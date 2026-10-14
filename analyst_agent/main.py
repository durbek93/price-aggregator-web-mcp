# -*- coding: utf-8 -*-
import logging
import asyncio
import re
from aiohttp import web

from aiogram import Bot, Dispatcher, types
from aiogram.types import BufferedInputFile
from aiogram.enums import ChatAction

import config
import chart_generator
import presentation_generator
from backend_client import (
    fetch_analysis_data,
    fetch_manufacturer_data,
    fetch_drug_data,
    fetch_system_summary,
    fetch_sales_data,
)
from gemini_service import (
    classify_user_request,
    generate_ai_report,
    generate_manufacturer_report,
    generate_drug_report,
    generate_general_qa_report,
    generate_sales_report,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("analyst_agent")

if not config.ANALYST_BOT_TOKEN:
    logger.error("ANALYST_BOT_TOKEN is not configured! Analyst Agent cannot start.")
    exit(1)

# Initialize bot and dispatcher
bot = Bot(token=config.ANALYST_BOT_TOKEN)
dp = Dispatcher()


def tokenize_html(text: str) -> list[str]:
    # Splits by HTML tags and newlines, keeping them as separate tokens
    tokens = re.split(r'(</?[a-zA-Z0-9]+(?:\s+[^>]*)?>|\n)', text)
    return [t for t in tokens if t != ""]


def get_tag_info(token: str):
    # Returns (is_tag, is_opening, tag_name)
    if not (token.startswith('<') and token.endswith('>')):
        return False, False, ""
    
    if token.startswith('</'):
        # Closing tag
        match = re.match(r'^</([a-zA-Z0-9]+)>$', token)
        if match:
            return True, False, match.group(1).lower()
    else:
        # Opening tag
        if token.endswith('/>'):
            return True, True, "" # Self-closing
        match = re.match(r'^<([a-zA-Z0-9]+)(?:\s+[^>]*)?>$', token)
        if match:
            return True, True, match.group(1).lower()
            
    return True, True, ""


def split_html_message(text: str, max_chars: int = 4000) -> list[str]:
    tokens = tokenize_html(text)
    
    chunks = []
    current_tokens = []
    stack = []  # holds tuples (tag_name, full_token)
    num_prepended = 0
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        is_tag, is_opening, tag_name = get_tag_info(token)
        
        # Calculate tags that would remain open if we split at this point
        temp_stack = list(stack)
        if is_tag and tag_name:
            if is_opening:
                temp_stack.append((tag_name, token))
            else:
                found = -1
                for idx in range(len(temp_stack) - 1, -1, -1):
                    if temp_stack[idx][0] == tag_name:
                        found = idx
                        break
                if found != -1:
                    temp_stack = temp_stack[:found]
                    
        closing_tags_len = sum(len(t_name) + 3 for t_name, _ in temp_stack)
        current_str_len = sum(len(t) for t in current_tokens)
        
        # If adding the token exceeds the max length (with closing tags)
        if current_str_len + len(token) + closing_tags_len > max_chars:
            # Find a good split point in current_tokens
            split_idx = -1
            # Search for newline first
            for idx in range(len(current_tokens) - 1, -1, -1):
                if current_tokens[idx] == '\n':
                    split_idx = idx + 1
                    break
            
            # If no newline, search for space in text tokens
            if split_idx == -1:
                for idx in range(len(current_tokens) - 1, -1, -1):
                    t = current_tokens[idx]
                    if not (t.startswith('<') and t.endswith('>')) and ' ' in t:
                        # Split the text token itself by space
                        parts = t.rsplit(' ', 1)
                        current_tokens[idx] = parts[0] + ' '
                        tokens.insert(i, parts[1])
                        split_idx = idx + 1
                        break
            
            # If still no split point, split at current boundary
            if split_idx == -1 or split_idx == 0:
                split_idx = len(current_tokens)
            
            # Prevent infinite loop: if split_idx would not consume any new tokens,
            # we force-consume the current token 'token'
            if split_idx <= num_prepended:
                current_tokens.append(token)
                if is_tag and tag_name:
                    if is_opening:
                        stack.append((tag_name, token))
                    else:
                        found = -1
                        for idx in range(len(stack) - 1, -1, -1):
                            if stack[idx][0] == tag_name:
                                found = idx
                                break
                        if found != -1:
                            stack = stack[:found]
                split_idx = len(current_tokens)
                i += 1
            
            # Reconstruct the stack up to split_idx
            split_stack = []
            for idx in range(split_idx):
                t = current_tokens[idx]
                t_is_tag, t_is_opening, t_tag_name = get_tag_info(t)
                if t_is_tag and t_tag_name:
                    if t_is_opening:
                        split_stack.append((t_tag_name, t))
                    else:
                        found = -1
                        for s_idx in range(len(split_stack) - 1, -1, -1):
                            if split_stack[s_idx][0] == t_tag_name:
                                found = s_idx
                                break
                        if found != -1:
                            split_stack = split_stack[:found]
            
            # Build current chunk
            chunk_tokens = current_tokens[:split_idx]
            closing_tags = "".join(f"</{t_name}>" for t_name, _ in reversed(split_stack))
            chunks.append("".join(chunk_tokens) + closing_tags)
            
            # Prepare remaining tokens for next chunk
            remaining_tokens = current_tokens[split_idx:]
            stack = split_stack
            num_prepended = len(stack)
            
            # Prepend active opening tags to next chunk
            current_tokens = []
            for _, open_tag_token in stack:
                current_tokens.append(open_tag_token)
            current_tokens.extend(remaining_tokens)
            
            # Reprocess current token
            continue
            
        else:
            current_tokens.append(token)
            if is_tag and tag_name:
                if is_opening:
                    stack.append((tag_name, token))
                else:
                    found = -1
                    for idx in range(len(stack) - 1, -1, -1):
                        if stack[idx][0] == tag_name:
                            found = idx
                            break
                    if found != -1:
                        stack = stack[:found]
            i += 1
            
    if current_tokens:
        closing_tags = "".join(f"</{t_name}>" for t_name, _ in reversed(stack))
        chunks.append("".join(current_tokens) + closing_tags)
        
    return chunks


class TypingContext:
    def __init__(self, bot, chat_id, interval=4.0):
        self.bot = bot
        self.chat_id = chat_id
        self.interval = interval
        self._task = None

    async def __aenter__(self):
        self._task = asyncio.create_task(self._keep_typing())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _keep_typing(self):
        try:
            while True:
                await self.bot.send_chat_action(chat_id=self.chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            pass


async def safe_delete_message(msg):
    try:
        await msg.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message: {e}")


async def send_report_in_chunks(message: types.Message, text: str, parse_mode: str = None):
    # Splits message into chunks of at most 4000 characters and sends them.
    # Note: Telegram message limit is 4096, so 4000 is a safe threshold.
    chunks = split_html_message(text, max_chars=4000)
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            await message.reply(chunk, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"Failed to send chunk with parse_mode={parse_mode}: {e}. Retrying as plain text...")
            await message.reply(chunk)


async def send_chat_report_in_chunks(chat_id: int | str, text: str, parse_mode: str = "HTML"):
    chunks = split_html_message(text, max_chars=4000)
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"Failed to send chunk to chat {chat_id} with parse_mode={parse_mode}: {e}. Retrying plain text...")
            await bot.send_message(chat_id=chat_id, text=chunk)


async def process_and_send_svodny_analysis(chat_id: int | str, user_id: str = "1", scope: str = "republic") -> bool:
    try:
        data = await fetch_analysis_data(scope=scope)
        if not data or not data.get("drugs"):
            logger.warning(f"No analysis data returned from backend for automated trigger (scope={scope}).")
            return False
        report_text = await generate_ai_report(data, include_deficit=False, scope=scope)
        await send_chat_report_in_chunks(chat_id, report_text, parse_mode="HTML")
        logger.info(f"Automated svodny report successfully sent to chat {chat_id} (scope={scope})")
        return True
    except Exception as e:
        logger.exception(f"Error generating automated svodny report: {e}")
        return False


async def handle_trigger_report(request: web.Request) -> web.Response:
    try:
        body = await request.json() if request.can_read_body else {}
    except Exception:
        body = {}
    
    auth_header = request.headers.get("X-Internal-API-Key", "")
    if auth_header and config.INTERNAL_API_KEY and auth_header != config.INTERNAL_API_KEY:
        return web.json_response({"error": "Unauthorized"}, status=401)
        
    chat_id = body.get("chat_id") or config.TELEGRAM_GROUP_ID
    user_id = str(body.get("user_id") or "1")
    scope = str(body.get("scope") or "republic")
    if not chat_id:
        return web.json_response({"error": "No chat_id provided and TELEGRAM_GROUP_ID not configured"}, status=400)
        
    logger.info(f"Received automated report trigger for chat_id={chat_id}, user_id={user_id}, scope={scope}")
    asyncio.create_task(process_and_send_svodny_analysis(chat_id, user_id, scope=scope))
    return web.json_response({"status": "ok", "message": "Report generation triggered"})


@dp.message()
async def handle_new_report_notification(message: types.Message):
    """Обрабатывает сообщения в закрытой группе и реагирует на уведомления от главного бота."""
    chat_id = message.chat.id
    text = message.text or message.caption or ""
    text_low = text.lower()
    
    logger.info(f"Incoming message from chat {chat_id} ({message.chat.type}): {text[:100]}")
    
    # 1. Проверяем ID группы (если настроен)
    if config.TELEGRAM_GROUP_ID and chat_id != config.TELEGRAM_GROUP_ID:
        logger.info(f"Ignored message: chat_id {chat_id} does not match TELEGRAM_GROUP_ID {config.TELEGRAM_GROUP_ID}")
        return
    
    # 2. Проверяем бота-получателя
    bot_info = await bot.get_me()
    bot_username = (bot_info.username or "lightprice_analyst_bot").lower()
    bot_mention = f"@{bot_username}"

    # Если команда или сообщение явно адресованы другому боту (например, @lightprice_aggr_bot), игнорируем
    if "@" in text_low:
        words_with_at = [w for w in text_low.split() if "@" in w]
        if any(w.startswith("@") and not w.startswith(bot_mention) for w in words_with_at):
            if bot_mention not in text_low:
                logger.info(f"Ignored message addressed to another bot: {text[:60]}")
                return

    is_private = message.chat.type == "private"
    is_mentioned = (
        bot_mention in text_low or 
        "@lightprice_analyst_bot" in text_low or 
        text_low.startswith(("аналитик,", "аналитик ", "аналитик\n", "аналитик:")) or
        " аналитик," in text_low or
        " аналитик " in text_low or
        " аналитик\n" in text_low or
        " аналитик:" in text_low
    )
    is_reply_to_me = bool(
        message.reply_to_message and 
        message.reply_to_message.from_user and 
        message.reply_to_message.from_user.id == bot_info.id
    )
    is_direct_command = (
        text_low.startswith((f"/fetch@{bot_username}", f"/clean@{bot_username}", f"/purge@{bot_username}")) or
        (is_private and text_low.startswith(("/fetch", "/download_prices", "/clean", "/purge"))) or
        "скачай последние прайсы" in text_low or
        "скачай прайсы" in text_low or
        "загрузи прайсы" in text_low or
        "очисти память" in text_low
    )
    
    if not (is_mentioned or is_reply_to_me or is_private or is_direct_command):
        logger.info("Ignored message: bot is not addressed (no mention, reply, or direct command).")
        return
        
    logger.info("Valid trigger message intercepted. Processing analysis report...")
    
    # 1. Отправляем временное сообщение о начале работы
    status_msg = await message.reply(
        "⏳ <b>Запрос принят.</b> Собираю данные и генерирую аналитический отчет, пожалуйста, подождите...",
        parse_mode="HTML"
    )
    
    # 2. Запускаем фоновый показ статуса "печатает"
    async with TypingContext(bot, chat_id):
        try:
            # Классифицируем запрос
            classification = await classify_user_request(text)
            req_type = classification.get("request_type")
            target = classification.get("target")
            days = classification.get("days", 3)
            date1 = classification.get("date1")
            date2 = classification.get("date2")
            
            wants_chart = classification.get("wants_chart", False)
            wants_presentation = classification.get("wants_presentation", False)

            if req_type == "database_info" or req_type == "general_qa":
                logger.info(f"Classified as {req_type} request")
                summary = await fetch_system_summary()
                report_text = await generate_general_qa_report(text, summary)
                await safe_delete_message(status_msg)
                logger.info("Sending general QA / DB info response...")
                await send_report_in_chunks(message, report_text, parse_mode="HTML")
                return

            elif req_type == "manufacturer" and target:
                logger.info(f"Classified as manufacturer request: {target} for {days} days")
                
                # Шаг 1: Запрашиваем исторические данные по производителю
                data = await fetch_manufacturer_data(target, days)
                if not data or not data.get("drugs"):
                    error_text = (
                        f"❌ Не удалось получить данные о ценах для производителя {target} за последние {days} дней."
                        if not data
                        else f"⚠️ Данные о ценах препаратов производителя {target} за последние {days} дней отсутствуют."
                    )
                    await safe_delete_message(status_msg)
                    await message.reply(error_text)
                    return
                    
                # Шаг 2: Генерируем специализированный отчет
                report_text = await generate_manufacturer_report(data, target, days)
                
                # Шаг 3: Удаляем временное сообщение и публикуем отчет
                await safe_delete_message(status_msg)
                logger.info("Sending manufacturer analytical report...")
                await send_report_in_chunks(message, report_text, parse_mode="HTML")

                if wants_chart:
                    chart_bytes = chart_generator.generate_price_trend_chart(data, target)
                    if chart_bytes:
                        photo = BufferedInputFile(chart_bytes, filename="manufacturer_prices.png")
                        await message.reply_photo(photo=photo, caption=f"📊 <b>Сравнение цен: {target}</b>", parse_mode="HTML")

                if wants_presentation:
                    sales_data = await fetch_sales_data() or {}
                    pptx_bytes = presentation_generator.build_analytics_presentation(sales_data, title=f"Аналитический отчёт: {target}")
                    if pptx_bytes:
                        doc = BufferedInputFile(pptx_bytes, filename=f"presentation_{target}.pptx")
                        await message.reply_document(document=doc, caption=f"📽 <b>Аналитическая презентация: {target} (.pptx)</b>", parse_mode="HTML")

                return

            elif req_type == "drug" and target:
                logger.info(f"Classified as drug request: {target} for {days} days")
                
                # Шаг 1: Запрашиваем исторические данные по препарату
                data = await fetch_drug_data(target, days)
                if not data or not data.get("drugs"):
                    error_text = (
                        f"❌ Не удалось получить данные о ценах для препарата «{target}» за последние {days} дней."
                        if not data
                        else f"⚠️ Данные о ценах для препарата «{target}» за последние {days} дней отсутствуют."
                    )
                    await safe_delete_message(status_msg)
                    await message.reply(error_text)
                    return
                    
                # Шаг 2: Генерируем специализированный отчет
                report_text = await generate_drug_report(data, target, days)
                
                # Шаг 3: Удаляем временное сообщение и публикуем отчет
                await safe_delete_message(status_msg)
                logger.info("Sending drug analytical report...")
                await send_report_in_chunks(message, report_text, parse_mode="HTML")

                if wants_chart:
                    chart_bytes = chart_generator.generate_price_trend_chart(data, target)
                    if chart_bytes:
                        photo = BufferedInputFile(chart_bytes, filename="drug_prices.png")
                        await message.reply_photo(photo=photo, caption=f"📊 <b>Цены по препарату: {target}</b>", parse_mode="HTML")

                if wants_presentation:
                    sales_data = await fetch_sales_data() or {}
                    pptx_bytes = presentation_generator.build_analytics_presentation(sales_data, title=f"Анализ рынка: {target}")
                    if pptx_bytes:
                        doc = BufferedInputFile(pptx_bytes, filename="drug_presentation.pptx")
                        await message.reply_document(document=doc, caption=f"📽 <b>Презентация по препарату: {target} (.pptx)</b>", parse_mode="HTML")

                return

            elif req_type == "sales":
                logger.info("Classified as sales request")
                data = await fetch_sales_data()
                if not data or (not data.get("by_distributor") and not data.get("by_product") and not data.get("summary")):
                    error_text = (
                        "❌ Не удалось получить данные о продажах с бэкенда."
                        if not data
                        else "⚠️ Данные о продажах в папке outputs/sales отсутствуют или не удалось распарсить Excel-файлы."
                    )
                    await safe_delete_message(status_msg)
                    await message.reply(error_text)
                    return

                report_text = await generate_sales_report(data, user_query=text)
                await safe_delete_message(status_msg)
                logger.info("Sending sales analytical report...")
                await send_report_in_chunks(message, report_text, parse_mode="HTML")

                if wants_chart or not (wants_chart or wants_presentation):  # По умолчанию высылаем график для продаж при прямо затребованном отчете
                    chart_bytes = chart_generator.generate_sales_chart(data)
                    if chart_bytes:
                        photo = BufferedInputFile(chart_bytes, filename="sales_dashboard.png")
                        await message.reply_photo(photo=photo, caption="📊 <b>Дашборд реализации по месяцам и долей дистрибьюторов</b>", parse_mode="HTML")

                if wants_presentation:
                    pptx_bytes = presentation_generator.build_analytics_presentation(data, title="Анализ продаж и остатков")
                    if pptx_bytes:
                        doc = BufferedInputFile(pptx_bytes, filename="sales_analytics.pptx")
                        await message.reply_document(document=doc, caption="📽 <b>Презентация по продажам (.pptx)</b>", parse_mode="HTML")

                return

            elif req_type == "fetch_prices":
                logger.info("Handling fetch_prices request in Analyst Agent")
                await safe_delete_message(status_msg)
                
                # Запускаем сборщик Scout Agent по HTTP
                try:
                    import urllib.request
                    url = "http://scout_agent:8080/fetch"
                    req = urllib.request.Request(url, method="POST")
                    req.add_header("X-Internal-API-Key", config.INTERNAL_API_KEY)
                    
                    loop = asyncio.get_running_loop()
                    def _send():
                        with urllib.request.urlopen(req, timeout=10.0) as resp:
                            return resp.status
                    st = await loop.run_in_executor(None, _send)
                    if st == 200:
                        await message.reply("⏳ <b>Запрос на скачивание прайс-листов получен.</b> Начинаю скачивать свежие прайсы (100% / 25%) со всех каналов дистрибьюторов...", parse_mode="HTML")
                    else:
                        await message.reply("❌ Ошибка при взаимодействии с Агентом-Сборщиком (Scout Agent).")
                except Exception as ex:
                    logger.exception(f"Error contacting Scout Agent: {ex}")
                    await message.reply(f"❌ Не удалось связаться со Scout Agent: {ex}")
                return

            elif req_type == "purge_memory":
                logger.info("Handling purge_memory request in Analyst Agent")
                await safe_delete_message(status_msg)
                await message.reply(
                    "⚠️ <b>Очистка памяти от старых прайс-листов</b>\n\n"
                    "Вы можете запустить процедуру очистки командой:\n"
                    "• <code>/clean 05.2026</code> (за май 2026)\n"
                    "• <code>/clean 05.2026-06.2026</code> (за май и июнь 2026)\n"
                    "• <code>/clean 01.05.2026-30.06.2026</code>\n\n"
                    "Бот покажет найденный объем файлов и запросит интерактивное подтверждение перед удалением.",
                    parse_mode="HTML"
                )
                return

            # Шаг 1: Запрашиваем дельту цен с бэкенда для общего отчета
            scope = "fergana" if any(w in text_low for w in ["ферган", "долин", "фергана"]) else "republic"
            data = await fetch_analysis_data(date1=date1, date2=date2, scope=scope)
            if not data or not data.get("drugs"):
                error_text = (
                    "❌ Не удалось получить данные анализа цен от бэкенда."
                    if not data
                    else f"⚠️ Бэкенд не вернул данных о ценах препаратов для анализа (scope={scope})."
                )
                await safe_delete_message(status_msg)
                await message.reply(error_text)
                return
                
            # Проверим, запрашивает ли пользователь отчет с дефицитом/дефектурой
            include_deficit = any(kw in text_low for kw in ["дефицит", "дефектур", "дефектура", "дефектурам", "нет в наличии", "отсутству"])
            logger.info(f"Generating report with include_deficit={include_deficit}, scope={scope}")
            
            # Шаг 2: Генерируем аналитику через Gemini 2.5 Flash
            report_text = await generate_ai_report(data, include_deficit=include_deficit, scope=scope)
            
            # Шаг 3: Удаляем временное сообщение и публикуем отчет
            await safe_delete_message(status_msg)
            logger.info("Sending analytical report to the group chat...")
            await send_report_in_chunks(message, report_text, parse_mode="HTML")

            if wants_chart:
                chart_title = "Анализ цен (Ферганская долина)" if scope == "fergana" else "Общий анализ цен"
                chart_bytes = chart_generator.generate_price_trend_chart(data, chart_title)
                if chart_bytes:
                    photo = BufferedInputFile(chart_bytes, filename="price_analysis.png")
                    await message.reply_photo(photo=photo, caption=f"📊 <b>{chart_title}</b>", parse_mode="HTML")

            if wants_presentation:
                sales_data = await fetch_sales_data() or {}
                pptx_bytes = presentation_generator.build_analytics_presentation(sales_data, title="Общий аналитический отчёт рынка")
                if pptx_bytes:
                    doc = BufferedInputFile(pptx_bytes, filename="market_summary.pptx")
                    await message.reply_document(document=doc, caption="📽 <b>Аналитическая презентация (.pptx)</b>", parse_mode="HTML")


        except Exception as e:
            logger.exception(f"Exception during report generation/sending: {e}")
            await safe_delete_message(status_msg)
            await message.reply(f"❌ Произошла ошибка во время обработки запроса: {str(e)}")


async def main():
    logger.info("Starting Analyst Agent bot and internal HTTP server...")
    bot_info = await bot.get_me()
    logger.info(f"Bot info: @{bot_info.username} (ID: {bot_info.id})")
    logger.info(f"Configured main bot ID: {config.MAIN_BOT_ID}")
    logger.info(f"Configured group ID: {config.TELEGRAM_GROUP_ID}")
    
    # Setup internal HTTP server on port 8002
    app = web.Application()
    app.router.add_post("/trigger_report", handle_trigger_report)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8002)
    await site.start()
    logger.info("Internal HTTP server started on 0.0.0.0:8002")

    try:
        # Start polling
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
