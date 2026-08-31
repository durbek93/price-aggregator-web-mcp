# -*- coding: utf-8 -*-
import os
import re
import asyncio
import logging
from datetime import datetime
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

async def send_scout_telegram_report(text: str):
    """Отправляет отчёт о скачанных файлах в групповой чат Telegram."""
    bot_token = config.TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    group_id = config.TELEGRAM_GROUP_ID or os.getenv("TELEGRAM_GROUP_ID", "")
    if not bot_token or not group_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_GROUP_ID not configured for scout notification.")
        return
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(
                url,
                json={"chat_id": group_id, "text": text, "parse_mode": "HTML"},
                timeout=15.0
            )
    except Exception as e:
        logger.error(f"Failed to send Telegram report from Scout Agent: {e}")


async def edit_telegram_message(chat_id: Optional[int], message_id: Optional[int], text: str):
    """Динамически обновляет сообщение в Telegram для отображения живого прогресса."""
    bot_token = config.TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token or not chat_id or not message_id:
        return
    try:
        url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
        async with httpx.AsyncClient() as client:
            await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "HTML"
                },
                timeout=10.0
            )
    except Exception as e:
        logger.debug(f"Failed to edit telegram progress message: {e}")


async def collect_latest_files(
    trigger_aggregation: bool = True,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None
) -> Tuple[bool, int]:
    """
    Опрашивает каналы дистрибьюторов, скачивает самые свежие прайс-листы (100% и 25%),
    загружает их на бэкенд и (опционально) запускает построение сводного прайса с живым отчетом.
    """
    logger.info(f"Starting collection of latest files from distributor channels (trigger_aggregation={trigger_aggregation})...")
    uploaded_ids = []
    downloaded_paths = []
    download_summary: Dict[str, List[str]] = {}
    
    # Пре-кэшируем диалоги, чтобы Pyrogram мог разрешить ID каналов, которых нет в локальной БД сессии
    try:
        logger.info("Pre-caching Pyrogram dialogs to resolve channel peer IDs...")
        async for dialog in app.get_dialogs(limit=100):
            pass
        logger.info("Dialog pre-caching completed successfully.")
    except Exception as e:
        logger.warning(f"Failed to pre-cache dialogs: {e}")
    
    total_channels = len(config.DISTRIBUTOR_CHANNELS)
    for ch_idx, channel in enumerate(config.DISTRIBUTOR_CHANNELS, 1):
        logger.info(f"Processing distributor channel/chat [{ch_idx}/{total_channels}]: {channel}")
        
        # Обновляем живой статус в Telegram
        if chat_id and message_id:
            percent = int(((ch_idx - 1) / total_channels) * 100)
            filled = (ch_idx - 1) * 10 // total_channels
            bar = "■" * filled + "□" * (10 - filled)
            progress_text = (
                f"⏳ <b>Сбор прайс-листов в процессе... [{ch_idx}/{total_channels}]</b>\n\n"
                f"🔍 <b>Опрашиваю канал:</b> <code>{channel}</code>\n"
                f"📊 <b>Прогресс:</b> <code>[{bar}] {percent}%</code>\n"
                f"📁 <b>Скачано файлов:</b> {len(uploaded_ids)}"
            )
            await edit_telegram_message(chat_id, message_id, progress_text)
            
        try:
            chat = await app.get_chat(channel)
            chat_title = chat.title or chat.first_name or str(channel)
            cleaned_name = clean_distributor_name(chat_title)
            logger.info(f"Cleaned distributor name: '{cleaned_name}' (original: '{chat_title}')")
            
            is_grand = (str(channel) == "-1001180237503" or channel == -1001180237503)
            is_luxe = (str(channel) == "vaksinabot" or "luxe" in str(cleaned_name).lower() or "люкс" in str(cleaned_name).lower())
            is_promotion = ("promotion" in str(cleaned_name).lower() or "промоушен" in str(cleaned_name).lower())
            is_biotek = (str(channel) == "-1003861704035" or channel == -1003861704035 or "biotek" in str(cleaned_name).lower() or "биотек" in str(cleaned_name).lower())
            if is_biotek:
                cleaned_name = "BIOTEK FARM"
            
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
                    
                    if is_grand:
                        caption_text = (message.caption or "").lower()
                        full_text = low_name + " " + caption_text
                        file_size = message.document.file_size or 0
                        
                        # 1. Пропускаем акционные файлы по ключевым словам и процентам скидок (-3%, - 3 %, чегирма)
                        is_promo = any(kw in full_text for kw in ["чегирма", "chegirma", "скидк", "акци", "promo", "bonus", "бонус", "уцен", "распродаж"]) or bool(re.search(r"-\s*\d+\s*%", full_text))
                        if is_promo:
                            logger.info(f"Skipping promotional/action file in Grand Pharm: {fname}")
                            continue
                            
                        # 2. Пропускаем усеченные файлы меньше 2 МБ (основные прайсы имеют размер ~16 МБ)
                        if file_size > 0 and file_size < 2000000:
                            logger.info(f"Skipping small file (<2MB) in Grand Pharm: {fname} ({file_size} bytes)")
                            continue
                            
                        # 3. Сопоставляем основные прайсы 100% и 25%
                        if "100" in low_name:
                            if not msg_100:
                                msg_100 = message
                        else:
                            if not msg_25:
                                msg_25 = message
                    else:  # is_promotion
                        if "100" in low_name:
                            if not msg_100:
                                msg_100 = message
                        elif "25" in low_name:
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
                        download_summary.setdefault(cleaned_name, []).append(target_name)
                
                if chat_id and message_id:
                    percent = int((ch_idx / total_channels) * 100)
                    filled = ch_idx * 10 // total_channels
                    bar = "■" * filled + "□" * (10 - filled)
                    saved_names = ", ".join([t[1] for t in targets])
                    progress_text = (
                        f"⏳ <b>Сбор прайс-листов в процессе... [{ch_idx}/{total_channels}]</b>\n\n"
                        f"🏢 <b>Дистрибьютор:</b> {cleaned_name}\n"
                        f"📥 <i>Скачан:</i> <code>{saved_names}</code>\n"
                        f"📊 <b>Прогресс:</b> <code>[{bar}] {percent}%</code>\n"
                        f"📁 <b>Всего скачано:</b> {len(uploaded_ids)} файлов"
                    )
                    await edit_telegram_message(chat_id, message_id, progress_text)
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
                        download_summary.setdefault(cleaned_name, []).append(target_name)
                continue

            is_meros = (str(channel) == "-1001367609205" or channel == -1001367609205 or "meros" in str(cleaned_name).lower() or "мерос" in str(cleaned_name).lower())
            candidates = []
            async for message in app.get_chat_history(channel, limit=1000):
                if not message.document:
                    continue
                    
                doc = message.document
                filename = doc.file_name or ""
                lower_filename = filename.lower()
                
                if not (lower_filename.endswith('.xlsx') or lower_filename.endswith('.xls') or lower_filename.endswith('.xlsb')):
                    continue
                
                caption_text = message.caption or ""
                text_to_check = (filename + " " + caption_text).lower()
                fergana_keywords = [
                    "ферган", "фарғон", "фаргон", "fargona", "farg'ona", "fargʼona"
                ]
                other_regions = [
                    "самарканд", "samarkand", "андижан", "andijan", "бухар", "bukhara",
                    "наманган", "namangan", "хорезм", "khorezm", "нукус", "nukus",
                    "карши", "karshi", "коканд", "kokand", "джизак", "jizzakh",
                    "навои", "navoi", "термез", "termez", "ургенч", "urgench", "хива", "khiva"
                ]
                tashkent_keywords = ["ташкент", "тошкент", "tashkent", "toshkent"]
                samarkand_keywords = ["самарканд", "samarkand"]
                
                has_fergana = any(f in text_to_check for f in fergana_keywords)
                has_samarkand = any(s in text_to_check for s in samarkand_keywords)
                has_tashkent = any(t in text_to_check for t in tashkent_keywords)
                
                other_non_samarkand = [r for r in other_regions if r not in samarkand_keywords]
                has_other_non_samarkand = any(r in text_to_check for r in other_non_samarkand)
                
                if is_meros:
                    if has_other_non_samarkand and not (has_fergana or has_tashkent or has_samarkand):
                        logger.info(f"File '{filename}' ignored for Meros (matches other region '{text_to_check}').")
                        continue
                else:
                    has_other_region = any(r in text_to_check for r in other_regions)
                    if not is_biotek and has_other_region and not (has_fergana or has_tashkent):
                        logger.info(f"File '{filename}' ignored (matches other region '{text_to_check}' and doesn't contain Fergana/Tashkent).")
                        continue
                
                file_size = doc.file_size or 0
                promo_pattern = re.compile(
                    r"\b(?:акци|скидк|распродаж|уцен|promo\b|action\b|sale\b|приход|остатк|бонус|bonus\b|презентац|косметик|гигиен|аптеч|дефицит|ограничен)",
                    re.IGNORECASE
                )
                
                # 1. Отсеиваем мини-акции и рекламные листовки малого размера (< 300 КБ)
                if file_size > 0 and file_size < 300000 and (promo_pattern.search(lower_filename) or promo_pattern.search(caption_text.lower())):
                    logger.info(f"Skipping small promotional file (<300KB) in {cleaned_name}: {filename} ({file_size} bytes)")
                    continue

                score = 100.0
                
                # Бонус за регионы
                if has_fergana:
                    score += 50.0
                elif has_tashkent:
                    score += 20.0
                elif has_samarkand:
                    score += 15.0
                elif not is_biotek:
                    score -= 70.0

                # Для небольших файлов штрафуем промо-слова, для полноценных каталогов (>500 КБ) слово в названии не отбрасывает файл
                if promo_pattern.search(lower_filename) or promo_pattern.search(caption_text.lower()):
                    if file_size < 500000:
                        score -= 50.0
                    else:
                        score -= 5.0
                        
                postpay_keywords = ["25%", "25 %", "25процент", "25 отсроч", "25 отср", "отсроч", "отср"]
                for kw in postpay_keywords:
                    if kw in lower_filename or kw in caption_text.lower():
                        score -= 80.0
                        break
                        
                prepay_keywords = ["100%", "100 %", "100процент", "100", "без отсрочки", "предоплат", "предопл", "без отср"]
                for kw in prepay_keywords:
                    if kw in lower_filename or kw in caption_text.lower():
                        score += 30.0
                        break
                        
                main_keywords = ["прайс", "price", "основной", "main"]
                for kw in main_keywords:
                    if kw in lower_filename:
                        score += 20.0
                        break
                
                # 2. Извлечение даты из имени файла (например, 25.08.2026, 25,08,2026, 25_08_2026, 25.08)
                date_match = re.search(r"(\d{1,2})[.,_](\d{1,2})(?:[.,_](\d{2,4}))?", filename)
                now = datetime.now()
                if date_match:
                    try:
                        d = int(date_match.group(1))
                        m = int(date_match.group(2))
                        if d == now.day and m == now.month:
                            score += 500.0  # Приоритет файла с сегодняшней датой
                        elif m == now.month and d == (now.day - 1):
                            score += 200.0  # Приоритет вчерашней даты
                    except Exception:
                        pass
                        
                # 3. Решающий вес фактора свежести времени сообщения (1 день = 100 баллов)
                score += (message.date.timestamp() / 864.0)
                region_tag = "tashkent"
                if is_meros and has_samarkand and not has_tashkent:
                    region_tag = "samarkand"
                candidates.append((score, message, region_tag))
                
            if not candidates:
                logger.warning(f"No valid price list candidates found in channel {channel}")
                continue
                
            if is_meros:
                tashkent_cands = [c for c in candidates if c[2] == "tashkent"]
                samarkand_cands = [c for c in candidates if c[2] == "samarkand"]
                if tashkent_cands:
                    tashkent_cands.sort(key=lambda x: x[0], reverse=True)
                    best_score, best_message, _ = tashkent_cands[0]
                    logger.info(f"Selected Tashkent price list for Meros Pharm: {best_message.document.file_name}")
                elif samarkand_cands:
                    samarkand_cands.sort(key=lambda x: x[0], reverse=True)
                    best_score, best_message, _ = samarkand_cands[0]
                    logger.info(f"Tashkent price list absent for Meros Pharm. Falling back to Samarkand price list: {best_message.document.file_name}")
                else:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    best_score, best_message, _ = candidates[0]
            else:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_score, best_message, _ = candidates[0]
            best_doc = best_message.document
            
            ext = Path(best_doc.file_name).suffix.lower()
            temp_filename = f"{cleaned_name}{ext}"
            
            path = await best_message.download(file_name=temp_filename)
            logger.info(f"Downloaded best file to: {path}")
            downloaded_paths.append(path)
            
            file_id = await upload_file_to_backend(path)
            if file_id:
                uploaded_ids.append(file_id)
                download_summary.setdefault(cleaned_name, []).append(temp_filename)
                if chat_id and message_id:
                    percent = int((ch_idx / total_channels) * 100)
                    filled = ch_idx * 10 // total_channels
                    bar = "■" * filled + "□" * (10 - filled)
                    progress_text = (
                        f"⏳ <b>Сбор прайс-листов в процессе... [{ch_idx}/{total_channels}]</b>\n\n"
                        f"🏢 <b>Дистрибьютор:</b> {cleaned_name}\n"
                        f"📥 <i>Скачан:</i> <code>{temp_filename}</code>\n"
                        f"📊 <b>Прогресс:</b> <code>[{bar}] {percent}%</code>\n"
                        f"📁 <b>Всего скачано:</b> {len(uploaded_ids)} файлов"
                    )
                    await edit_telegram_message(chat_id, message_id, progress_text)
                
        except Exception as e:
            logger.exception(f"Error processing channel {channel}: {e}")
            
    # В зависимости от флага trigger_aggregation либо вызываем сборку, либо отправляем отчёт о скачивании
    success = False
    if uploaded_ids:
        if trigger_aggregation:
            logger.info(f"Successfully collected and uploaded {len(uploaded_ids)} files. Triggering aggregation...")
            if chat_id and message_id:
                final_msg = (
                    f"✅ <b>Сбор файлов завершен!</b>\n\n"
                    f"📊 Всего скачано: <b>{len(uploaded_ids)} файлов</b> с {total_channels} каналов.\n"
                    f"⚙️ <i>Запускаю формирование сводного прайса...</i>"
                )
                await edit_telegram_message(chat_id, message_id, final_msg)
            success = await trigger_aggregation_task(uploaded_ids)
        else:
            logger.info(f"Successfully collected and uploaded {len(uploaded_ids)} files (download-only). Sending Telegram report...")
            success = True
            lines = [
                "✅ <b>Скачивание прайс-листов завершено!</b>\n",
                "📋 <b>Скачанные прайсы по каналам:</b>"
            ]
            for dist_name, file_names in download_summary.items():
                files_str = ", ".join(f"<code>{fn}</code>" for fn in file_names)
                lines.append(f"• <b>{dist_name}</b>: {files_str}")
            
            lines.append(f"\n📊 <b>Итого скачано и сохранено на сервере:</b> {len(uploaded_ids)} файлов.")
            lines.append("<i>Сводный прайс-лист не формировался.</i>")
            
            report_text = "\n".join(lines)
            if chat_id and message_id:
                await edit_telegram_message(chat_id, message_id, report_text)
            else:
                await send_scout_telegram_report(report_text)
    else:
        logger.warning("No files were successfully collected and uploaded.")
        no_files_msg = "⚠️ <b>Не удалось скачать ни одного нового прайс-листа с каналов.</b>"
        if chat_id and message_id:
            await edit_telegram_message(chat_id, message_id, no_files_msg)
        elif not trigger_aggregation:
            await send_scout_telegram_report(no_files_msg)
        
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
    """Мини HTTP-сервер для обработки POST /collect и POST /fetch от бота."""
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

        chat_id = None
        message_id = None
        if "\r\n\r\n" in message:
            body_str = message.split("\r\n\r\n", 1)[1]
            if body_str:
                try:
                    import json
                    body_json = json.loads(body_str)
                    chat_id = body_json.get("chat_id")
                    message_id = body_json.get("message_id")
                except Exception:
                    pass
            
        if method == "POST" and path == "/collect":
            logger.info(f"Received HTTP /collect request (chat_id={chat_id}, message_id={message_id}). Starting full collection flow...")
            asyncio.create_task(run_collect_flow(trigger_aggregation=True, chat_id=chat_id, message_id=message_id))
            
            response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 22\r\n\r\n{\"status\":\"initiated\"}"
            writer.write(response.encode())
            await writer.drain()
        elif method == "POST" and path == "/fetch":
            logger.info(f"Received HTTP /fetch request (chat_id={chat_id}, message_id={message_id}). Starting download-only flow...")
            asyncio.create_task(run_collect_flow(trigger_aggregation=False, chat_id=chat_id, message_id=message_id))
            
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

async def run_collect_flow(
    trigger_aggregation: bool = True,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None
):
    """Запускает процедуру сбора: опрос бота-дистрибьютора + сбор всех прайсов с живым прогрессом."""
    logger.info(f"Starting run_collect_flow (trigger_aggregation={trigger_aggregation}, chat_id={chat_id})...")
    if config.DEMAND_BOT_USERNAME:
        if chat_id and message_id:
            await edit_telegram_message(
                chat_id,
                message_id,
                f"🤖 <b>Запрашиваю актуальный прайс у бота @{config.DEMAND_BOT_USERNAME}...</b>\n<i>Ожидаем ответ бота (~30 сек)...</i>"
            )
        try:
            await trigger_demand_bot()
            # Даем боту время ответить и прислать файл
            logger.info("Waiting 30 seconds for demand bot to respond...")
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error during triggering demand bot in flow: {e}")
    await collect_latest_files(
        trigger_aggregation=trigger_aggregation,
        chat_id=chat_id,
        message_id=message_id
    )

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

