# -*- coding: utf-8 -*-
import os
import re
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import httpx
from pyrogram import Client, filters
from pyrogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("scout_agent")

app = Client(
    "scout_agent",
    api_id=config.TELEGRAM_API_ID,
    api_hash=config.TELEGRAM_API_HASH,
    phone_number=config.TELEGRAM_PHONE,
    password=config.TELEGRAM_PASSWORD,
    workdir="/app"
)

from api_client import upload_file_to_backend, trigger_aggregation_task

def clean_distributor_name(title: str) -> str:
    """Очищает имя канала от региональных и служебных слов."""
    t = title
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"\[.*?\]", "", t)
    
    words_to_remove = [
        r"\bташкент\b", r"\btashkent\b",
        r"\bгрупп\w*\b", r"\bgroup\b",
        r"\bканал\b", r"\bchannel\b",
        r"\bпрайс\w*\b", r"\bprice\w*\b",
        r"\bофициальный\b", r"\bofficial\b",
        r"\bинфо\b", r"\binfo\b",
        r"\bооо\b", r"\bllc\b"
    ]
    for pattern in words_to_remove:
        t = re.sub(pattern, "", t, flags=re.IGNORECASE)
    
    t = re.sub(r"[\|\-\_\,\.\:\;\#\*\+\(\)\{\}\[\]\"\'\`\«\»]", " ", t)
    t = " ".join(t.split())
    return t or title

async def collect_latest_files() -> Tuple[bool, int]:
    """
    Опрашивает каналы дистрибьюторов (20 последних сообщений в каждом),
    выбирает лучший прайс-лист со 100% предоплатой, скачивает,
    переименовывает в {Cleaned_Distributor_Name}.xlsx и загружает на бэкенд.
    """
    logger.info("Starting collection of latest files from distributor channels...")
    uploaded_ids = []
    downloaded_paths = []
    
    # Пре-кэшируем диалоги, чтобы Pyrogram мог разрешить ID каналов, которых нет в локальной БД сессии
    try:
        logger.info("Pre-caching Pyrogram dialogs to resolve channel peer IDs...")
        async for dialog in app.get_dialogs(limit=100):
            pass
        logger.info("Dialog pre-caching completed successfully.")
    except Exception as e:
        logger.warning(f"Failed to pre-cache dialogs: {e}")
    
    for channel in config.DISTRIBUTOR_CHANNELS:
        logger.info(f"Processing distributor channel/chat: {channel}")
        try:
            chat = await app.get_chat(channel)
            chat_title = chat.title or chat.first_name or str(channel)
            cleaned_name = clean_distributor_name(chat_title)
            logger.info(f"Cleaned distributor name: '{cleaned_name}' (original: '{chat_title}')")
            
            is_grand = (str(channel) == "-1001180237503" or channel == -1001180237503)
            is_luxe = (str(channel) == "vaksinabot" or "luxe" in str(cleaned_name).lower() or "люкс" in str(cleaned_name).lower())
            is_promotion = ("promotion" in str(cleaned_name).lower() or "промоушен" in str(cleaned_name).lower())
            
            if is_grand or is_promotion:
                msg_100 = None
                msg_25 = None
                async for message in app.get_chat_history(channel, limit=1000):
                    if not message.document:
                        continue
                    fname = message.document.file_name or ""
                    low_name = fname.lower()
                    if not (low_name.endswith('.xlsx') or low_name.endswith('.xls') or low_name.endswith('.xlsb')):
                        continue
                    
                    if "100" in low_name:
                        if not msg_100:
                            msg_100 = message
                    else:
                        if is_promotion:
                            if "25" in low_name:
                                if not msg_25:
                                    msg_25 = message
                        else:  # is_grand
                            if not msg_25:
                                msg_25 = message
                            
                    if msg_100 and msg_25:
                        break
                
                targets = []
                if is_grand:
                    if msg_100:
                        targets.append((msg_100, "GRAND PHARM 100%.xlsx"))
                    if msg_25:
                        targets.append((msg_25, "GRAND PHARM 25%.xlsx"))
                else:  # is_promotion
                    if msg_100:
                        targets.append((msg_100, "DRUG PROMOTION 100%.xlsx"))
                    if msg_25:
                        targets.append((msg_25, "DRUG PROMOTION 25%.xlsx"))
                    
                if not targets:
                    logger.warning(f"No files found in {channel}")
                    continue
                    
                for msg, target_name in targets:
                    path = await msg.download(file_name=target_name)
                    logger.info(f"Downloaded file: {path}")
                    downloaded_paths.append(path)
                    file_id = await upload_file_to_backend(path)
                    if file_id:
                        uploaded_ids.append(file_id)
                continue
                
            elif is_luxe:
                msg_100 = None
                msg_25 = None
                async for message in app.get_chat_history(channel, limit=1000):
                    if not message.document:
                        continue
                    fname = message.document.file_name or ""
                    low_name = fname.lower()
                    if not (low_name.endswith('.xlsx') or low_name.endswith('.xls') or low_name.endswith('.xlsb')):
                        continue
                    
                    if "100" in low_name:
                        if not msg_100:
                            msg_100 = message
                    elif "завод" in low_name or "zavod" in low_name or "25" in low_name:
                        if not msg_25:
                            msg_25 = message
                            
                    if msg_100 and msg_25:
                        break
                
                targets = []
                if msg_100:
                    targets.append((msg_100, "PHARM LUXE 100%.xlsx"))
                if msg_25:
                    targets.append((msg_25, "PHARM LUXE 25%.xlsx"))
                    
                if not targets:
                    logger.warning(f"No Pharm Luxe files found in {channel}")
                    continue
                    
                for msg, target_name in targets:
                    path = await msg.download(file_name=target_name)
                    logger.info(f"Downloaded Pharm Luxe file: {path}")
                    downloaded_paths.append(path)
                    file_id = await upload_file_to_backend(path)
                    if file_id:
                        uploaded_ids.append(file_id)
                continue

            candidates = []
            async for message in app.get_chat_history(channel, limit=1000):
                if not message.document:
                    continue
                    
                doc = message.document
                filename = doc.file_name or ""
                lower_filename = filename.lower()
                
                # 1. Проверка формата Excel
                if not (lower_filename.endswith('.xlsx') or lower_filename.endswith('.xls') or lower_filename.endswith('.xlsb')):
                    continue
                
                # Очищаем имя от неразрывных пробелов и т.д.
                caption_text = message.caption or ""
                logger.info(f"Excel file found: '{filename}' (caption: '{caption_text}')")
                
                # 2. Умный региональный фильтр: исключаем другие регионы, если нет упоминания Ташкента
                # Исключаем chat_title из проверки, чтобы не блокировать каналы с региональными именами (например, Biotek Fergana)
                text_to_check = (filename + " " + caption_text).lower()
                other_regions = ["самарканд", "samarkand", "андижан", "andijan", "бухар", "bukhara", "ферган", "fergana", "наманган", "namangan", "хорезм", "khorezm", "нукус", "nukus", "карши", "karshi", "коканд", "kokand", "джизак", "jizzakh", "навои", "navoi", "термез", "termez", "ургенч", "urgench", "хива", "khiva"]
                has_other_region = any(r in text_to_check for r in other_regions)
                has_tashkent = any(t in text_to_check for t in ["ташкент", "tashkent"])
                
                if has_other_region and not has_tashkent:
                    logger.info(f"File '{filename}' ignored (matches other region and doesn't contain Tashkent/Ташкент).")
                    continue
                
                # 3. Скоринг для выбора основного 100% прайса
                score = 100.0
                
                # Акции / Распродажи / Приходы / Дефициты
                # Используем регулярное выражение с границами слов, чтобы слово "promotion" не матчилось на "promo"
                promo_pattern = re.compile(
                    r"\b(?:акци|скидк|распродаж|уцен|promo\b|action\b|sale\b|приход|остатк|бонус|bonus\b|презентац|косметик|гигиен|аптеч|дефицит|ограничен|спец)",
                    re.IGNORECASE
                )
                if promo_pattern.search(lower_filename) or promo_pattern.search(caption_text.lower()):
                    score -= 60.0
                        
                # 25% предоплата / отсрочка
                postpay_keywords = ["25%", "25 %", "25процент", "25 отсроч", "25 отср", "отсроч", "отср"]
                for kw in postpay_keywords:
                    if kw in lower_filename or kw in caption_text.lower():
                        score -= 80.0
                        break
                        
                # 100% предоплата / без отсрочки
                prepay_keywords = ["100%", "100 %", "100процент", "100", "без отсрочки", "предоплат", "предопл", "без отср"]
                for kw in prepay_keywords:
                    if kw in lower_filename or kw in caption_text.lower():
                        score += 30.0
                        break
                        
                # Упоминание прайс/основной
                main_keywords = ["прайс", "price", "основной", "main"]
                for kw in main_keywords:
                    if kw in lower_filename:
                        score += 20.0
                        break
                        
                # Бонус за свежесть (message.date.timestamp() / 86400.0)
                score += (message.date.timestamp() / 86400.0)
                
                candidates.append((score, message))
                logger.info(f"Found candidate: '{filename}' | Score: {score:.2f}")
                
            if not candidates:
                logger.warning(f"No valid price list candidates found in channel {channel}")
                continue
                
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_message = candidates[0]
            best_doc = best_message.document
            
            logger.info(f"Selected best price list: '{best_doc.file_name}' with score {best_score:.2f}")
            
            ext = Path(best_doc.file_name).suffix.lower()
            temp_filename = f"{cleaned_name}{ext}"
            
            path = await best_message.download(file_name=temp_filename)
            logger.info(f"Downloaded best file to: {path}")
            downloaded_paths.append(path)
            
            file_id = await upload_file_to_backend(path)
            if file_id:
                uploaded_ids.append(file_id)
                
        except Exception as e:
            logger.exception(f"Error processing channel {channel}: {e}")
            
    # Запускаем сборку
    success = False
    if uploaded_ids:
        logger.info(f"Successfully collected and uploaded {len(uploaded_ids)} files. Triggering aggregation...")
        success = await trigger_aggregation_task(uploaded_ids)
    else:
        logger.warning("No files were successfully collected and uploaded.")
        
    # Удаляем временные локальные файлы
    for path in downloaded_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Deleted temporary local file: {path}")
        except Exception as e:
            logger.error(f"Failed to delete temp file {path}: {e}")
            
    return success, len(uploaded_ids)

async def handle_http_request(reader, writer):
    """Мини HTTP-сервер для обработки POST /collect от главного бота."""
    try:
        data = await reader.read(4096)
        message = data.decode()
        if not message:
            writer.close()
            return
            
        lines = message.split("\r\n")
        if not lines:
            writer.close()
            return
            
        request_line = lines[0]
        parts = request_line.split()
        if len(parts) < 2:
            writer.close()
            return
            
        method, path = parts[0], parts[1]
        
        is_authorized = False
        for line in lines[1:]:
            if line.lower().startswith("x-internal-api-key:"):
                key_val = line.split(":", 1)[1].strip()
                if key_val == config.INTERNAL_API_KEY:
                    is_authorized = True
                    break
        
        if not is_authorized:
            logger.warning(f"Unauthorized HTTP request: {request_line}")
            response = "HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nContent-Length: 30\r\n\r\n{\"error\":\"Unauthorized key\"}"
            writer.write(response.encode())
            await writer.drain()
            writer.close()
            return
            
        if method == "POST" and path == "/collect":
            logger.info("Received HTTP /collect request. Starting background collection flow...")
            asyncio.create_task(run_collect_flow())
            
            response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 22\r\n\r\n{\"status\":\"initiated\"}"
            writer.write(response.encode())
            await writer.drain()
        else:
            response = "HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nContent-Length: 25\r\n\r\n{\"error\":\"Not Found\"}"
            writer.write(response.encode())
            await writer.drain()
            
    except Exception as e:
        logger.exception(f"Error handling HTTP request: {e}")
        try:
            response = "HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\nContent-Length: 32\r\n\r\n{\"error\":\"Internal error\"}"
            writer.write(response.encode())
            await writer.drain()
        except Exception:
            pass
    finally:
        writer.close()

async def trigger_demand_bot():
    """Сценарий В: Автоматический запрос у бота-дистрибьютора."""
    if not config.DEMAND_BOT_USERNAME:
        logger.info("On-demand bot requests disabled (DEMAND_BOT_USERNAME not configured).")
        return
        
    logger.info(f"Triggering on-demand price request for bot: @{config.DEMAND_BOT_USERNAME}")
    try:
        await app.send_message(config.DEMAND_BOT_USERNAME, "/start")
        await asyncio.sleep(30)
        
        async for msg in app.get_chat_history(config.DEMAND_BOT_USERNAME, limit=1):
            if msg.reply_markup:
                if hasattr(msg.reply_markup, "inline_keyboard") and msg.reply_markup.inline_keyboard:
                    for row in msg.reply_markup.inline_keyboard:
                        for button in row:
                            btn_text = button.text.lower()
                            if "ташкент" in btn_text or "tashkent" in btn_text:
                                logger.info(f"Clicking inline button: '{button.text}'")
                                await msg.click(button.text)
                                return
                elif hasattr(msg.reply_markup, "keyboard") and msg.reply_markup.keyboard:
                    for row in msg.reply_markup.keyboard:
                        for button in row:
                            if isinstance(button, str):
                                btn_text = button
                            elif hasattr(button, "text"):
                                btn_text = button.text
                            else:
                                btn_text = str(button)
                            
                            if "ташкент" in btn_text.lower() or "tashkent" in btn_text.lower():
                                logger.info(f"Sending keyboard command: '{btn_text}'")
                                await app.send_message(config.DEMAND_BOT_USERNAME, btn_text)
                                return
        logger.warning("No button matching 'Tashkent' / 'Ташкент' found in the bot's reply.")
    except Exception as e:
        logger.exception(f"Failed to query on-demand bot: {e}")

async def run_collect_flow():
    """Запускает полную процедуру сбора: опрос бота-дистрибьютора + сбор всех прайсов."""
    logger.info("Starting run_collect_flow...")
    if config.DEMAND_BOT_USERNAME:
        try:
            await trigger_demand_bot()
            # Даем боту время ответить и прислать файл
            logger.info("Waiting 30 seconds for demand bot to respond...")
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error during triggering demand bot in flow: {e}")
    await collect_latest_files()

async def main():
    logger.info("Starting Scout Agent (userbot)...")
    
    session_exists = os.path.exists("/app/scout_agent.session")
    if not session_exists:
        logger.warning(
            "Session file '/app/scout_agent.session' not found! "
            "If this is running inside docker-compose without interactive TTY, it will fail. "
            "Please run it once interactively using:\n"
            "docker compose run --rm -it scout_agent python main.py"
        )
        
    await app.start()
    logger.info("Scout Agent is logged in and running.")
    
    scheduler = AsyncIOScheduler()
    if config.DEMAND_BOT_USERNAME:
        cron_trigger = CronTrigger.from_crontab(config.DEMAND_BOT_TRIGGER_CRON)
        scheduler.add_job(run_collect_flow, cron_trigger)
        logger.info(
            f"Scheduled collection flow (including bot request to @{config.DEMAND_BOT_USERNAME}) "
            f"with cron: '{config.DEMAND_BOT_TRIGGER_CRON}'"
        )
    scheduler.start()
    
    logger.info("Starting HTTP Server on port 8080...")
    server = await asyncio.start_server(handle_http_request, "0.0.0.0", 8080)
    
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())

