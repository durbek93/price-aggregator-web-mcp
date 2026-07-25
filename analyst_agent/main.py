# -*- coding: utf-8 -*-
import logging
import asyncio
import re

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatAction

import config
from backend_client import (
    fetch_analysis_data,
    fetch_manufacturer_data,
    fetch_drug_data,
    fetch_system_summary,
)
from gemini_service import (
    classify_user_request,
    generate_ai_report,
    generate_manufacturer_report,
    generate_drug_report,
    generate_general_qa_report,
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
    
    # 3. Проверяем упоминание нашего бота-аналитика
    bot_info = await bot.get_me()
    bot_mention = f"@{bot_info.username}"
    
    is_mentioned = (
        bot_mention in text_low or 
        "@lightprice_analyst_bot" in text_low or 
        "аналитик" in text_low
    )
    is_from_main_bot = (message.from_user and message.from_user.id == config.MAIN_BOT_ID)
    
    if not is_mentioned and not is_from_main_bot:
        logger.info("Ignored message: not from main bot and bot is not mentioned.")
        return
        
    # 4. Проверяем триггерный текст от бэкенда или ключевые слова (если бот не был прямо упомянут)
    has_trigger_keyword = any(
        kw in text_low
        for kw in [
            "сводный прайс-лист собран автоматически",
            "отчет",
            "анализ",
            "изменени",
            "дефицит",
            "аналитик",
            "прайс",
            "файл",
            "база",
            "бд",
            "какие",
            "покажи",
            "сводн",
        ]
    )
    if not (is_mentioned or is_from_main_bot or message.chat.type == "private" or has_trigger_keyword):
        logger.info("Ignored message: no trigger keyword found and bot is not directly addressed.")
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
                return

            # Шаг 1: Запрашиваем дельту цен с бэкенда для общего отчета
            data = await fetch_analysis_data(date1=date1, date2=date2)
            if not data or not data.get("drugs"):
                error_text = (
                    "❌ Не удалось получить данные анализа цен от бэкенда."
                    if not data
                    else "⚠️ Бэкенд не вернул данных о ценах препаратов для анализа (список пуст)."
                )
                await safe_delete_message(status_msg)
                await message.reply(error_text)
                return
                
            # Проверим, запрашивает ли пользователь отчет с дефицитом
            include_deficit = "дефицит" in text_low
            logger.info(f"Generating report with include_deficit={include_deficit}")
            
            # Шаг 2: Генерируем аналитику через Gemini 2.5 Flash
            report_text = await generate_ai_report(data, include_deficit=include_deficit)
            
            # Шаг 3: Удаляем временное сообщение и публикуем отчет
            await safe_delete_message(status_msg)
            logger.info("Sending analytical report to the group chat...")
            await send_report_in_chunks(message, report_text, parse_mode="HTML")

        except Exception as e:
            logger.exception(f"Exception during report generation/sending: {e}")
            await safe_delete_message(status_msg)
            await message.reply(f"❌ Произошла ошибка во время обработки запроса: {str(e)}")


async def main():
    logger.info("Starting Analyst Agent bot...")
    bot_info = await bot.get_me()
    logger.info(f"Bot info: @{bot_info.username} (ID: {bot_info.id})")
    logger.info(f"Configured main bot ID: {config.MAIN_BOT_ID}")
    logger.info(f"Configured group ID: {config.TELEGRAM_GROUP_ID}")
    
    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
