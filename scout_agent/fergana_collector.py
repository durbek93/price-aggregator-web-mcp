# -*- coding: utf-8 -*-
"""Автономный модуль сбора прайс-листов местных оптовиков Ферганской долины."""

import os
import re
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import httpx
from pyrogram import Client

import config
from fergana_channels import FERGANA_CHANNELS_CONFIG, FERGANA_NAME_BY_ID
from api_client import upload_file_to_backend, trigger_aggregation_task

logger = logging.getLogger("scout_agent.fergana_collector")


async def send_fergana_telegram_report(text: str):
    """Отправляет отчёт о прайсах Ферганской долины в группу Telegram."""
    bot_token = config.TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    group_id = config.TELEGRAM_GROUP_ID or os.getenv("TELEGRAM_GROUP_ID", "")
    if not bot_token or not group_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_GROUP_ID not configured for fergana notification.")
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
        logger.error(f"Failed to send Fergana report to Telegram: {e}")


async def edit_progress_message(chat_id: Optional[int], message_id: Optional[int], text: str):
    """Обновляет статусное сообщение в Telegram чате."""
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
        logger.debug(f"Failed to edit progress message: {e}")


async def collect_fergana_files(
    app: Client,
    trigger_aggregation: bool = True,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None
) -> Tuple[bool, int]:
    """Опрашивает каналы/группы 17 оптовиков Ферганской долины,

    скачивает свежие прайсы, загружает их на бэкенд и запускает сборку сводного
    прайса Долины.
    """
    logger.info("Starting collection of price lists from Fergana Valley distributors...")
    uploaded_ids: List[int] = []
    download_summary: Dict[str, str] = {}
    errors_summary: List[str] = []

    total_channels = len(FERGANA_CHANNELS_CONFIG)

    # 1. Предварительное кэширование диалогов
    try:
        logger.info("Pre-caching dialogs for Fergana channels resolution...")
        async for _ in app.get_dialogs(limit=500):
            pass
    except Exception as e:
        logger.warning(f"Dialog pre-caching warning: {e}")

    for idx, item in enumerate(FERGANA_CHANNELS_CONFIG, 1):
        dist_name = item["name"]
        channel_id = item["channel_id"]
        logger.info(f"[{idx}/{total_channels}] Checking Fergana distributor: {dist_name} ({channel_id})")

        if chat_id and message_id:
            percent = int(((idx - 1) / total_channels) * 100)
            filled = (idx - 1) * 10 // total_channels
            bar = "■" * filled + "□" * (10 - filled)
            progress_text = (
                f"🍇 <b>[ФЕРГАНСКАЯ ДОЛИНА] Сбор прайсов... [{idx}/{total_channels}]</b>\n\n"
                f"🔍 <b>Опрашиваю:</b> {dist_name}\n"
                f"📊 <b>Прогресс:</b> <code>[{bar}] {percent}%</code>\n"
                f"📁 <b>Скачано:</b> {len(uploaded_ids)} файлов"
            )
            await edit_progress_message(chat_id, message_id, progress_text)

        try:
            best_msg = None
            best_score = -1.0
            best_filename = ""

            async for message in app.get_chat_history(channel_id, limit=200):
                if not message.document:
                    continue

                fname = message.document.file_name or ""
                low_name = fname.lower()
                if not (low_name.endswith(".xlsx") or low_name.endswith(".xls") or low_name.endswith(".xlsb")):
                    continue

                file_size = message.document.file_size or 0
                caption = (message.caption or "").lower()
                full_text = f"{low_name} {caption}"

                # Базовый вес: размер файла и дата
                score = 50.0
                if file_size > 100000:  # > 100 КБ - скорее всего полный прайс
                    score += 30.0
                if any(w in full_text for w in ["прайс", "price", "optom", "оптом", "каталог"]):
                    score += 20.0
                if any(w in full_text for w in ["скидк", "акци", "уцен", "promo"]):
                    score -= 15.0

                # Специальные правила для Аззам (без 100%) и Верона (только 100%)
                is_azzam = ("аззам" in dist_name.lower())
                is_verona = ("верона" in dist_name.lower())
                has_100 = any(w in full_text for w in ["100%", "100 %", "100процент", "100"])

                if is_azzam and has_100:
                    # Для Аззам берём прайс БЕЗ 100%
                    continue

                if is_verona:
                    # Для Верона берём прайс ТОЛЬКО 100%
                    if has_100:
                        score += 50.0
                    else:
                        score -= 50.0

                if score > best_score:
                    best_score = score
                    best_msg = message
                    best_filename = fname

                # Если нашли свежий файл больше 150 КБ со словом прайс - он подходит отлично
                if best_score >= 90.0:
                    break

            if not best_msg:
                logger.warning(f"No suitable Excel price file found in {dist_name} ({channel_id})")
                errors_summary.append(f"⚠️ {dist_name}: файл Excel не найден")
                continue

            from pathlib import Path
            fergana_dir = Path("/app/downloads/fergana")
            fergana_dir.mkdir(parents=True, exist_ok=True)
            
            orig_ext = Path(best_filename).suffix.lower() if best_filename else ".xlsx"
            if orig_ext not in [".xlsx", ".xls"]:
                orig_ext = ".xlsx"
            target_filename = f"{dist_name}{orig_ext}"
            target_path = str(fergana_dir / target_filename)
            saved_path = await best_msg.download(file_name=target_path)
            logger.info(f"Downloaded file for {dist_name}: {saved_path} (original: {best_filename})")

            file_id = await upload_file_to_backend(saved_path, subfolder="fergana")
            if file_id:
                uploaded_ids.append(file_id)
                download_summary[dist_name] = target_filename
                logger.info(f"File for {dist_name} registered with Backend ID: {file_id}")
            else:
                errors_summary.append(f"⚠️ {dist_name}: ошибка загрузки на сервер")

            # Мгновенно удаляем временный файл из scout_agent/downloads
            try:
                if os.path.exists(saved_path):
                    os.remove(saved_path)
                    logger.info(f"Cleaned up temporary download file: {saved_path}")
            except Exception as ex:
                logger.warning(f"Failed to remove temp file {saved_path}: {ex}")

        except Exception as e:
            logger.error(f"Error accessing channel for {dist_name} ({channel_id}): {e}")
            errors_summary.append(f"❌ {dist_name}: {str(e)[:50]}")

    success = len(uploaded_ids) > 0
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Формируем итоговый отчёт для Telegram группы
    if uploaded_ids:
        if trigger_aggregation:
            logger.info(f"Collected {len(uploaded_ids)} Fergana files. Triggering svodny_fergana aggregation...")
            await trigger_aggregation_task(uploaded_ids, task_type="svodny_fergana")

        action_title = "Сбор и агрегация прайс-листов завершены!" if trigger_aggregation else "Скачивание прайс-листов завершено (режим fetch)!"
        lines = [
            f"🍇 <b>[ФЕРГАНСКАЯ ДОЛИНА] {action_title}</b>",
            f"📅 <b>Дата:</b> {now_str}",
            f"📊 <b>Собрано оптовиков:</b> {len(uploaded_ids)} из {total_channels}\n",
            "<b>Список полученных прайсов (папка <code>fergana</code>):</b>"
        ]
        for name in download_summary.keys():
            lines.append(f"  ✅ <code>{name}</code>")

        if errors_summary:
            lines.append("\n<b>Не удалось получить:</b>")
            for err in errors_summary[:5]:
                lines.append(f"  {err}")

        if trigger_aggregation:
            lines.append(f"\n⏳ <i>Запущен процесс формирования сводного прайса Долины...</i>")
        else:
            lines.append(f"\n📁 <i>Файлы сохранены на сервере в папке <code>fergana</code>. Для сборки сводного прайса используйте команду /just_collect_fergana</i>")

        await send_fergana_telegram_report("\n".join(lines))
    else:
        logger.warning("No files collected for Fergana Valley.")
        report_text = (
            "⚠️ <b>[ФЕРГАНСКАЯ ДОЛИНА] Сбор прайс-листов:</b>\n\n"
            "Не удалось найти или скачать свежие файлы из каналов местных оптовиков.\n"
            + "\n".join(errors_summary[:5])
        )
        await send_fergana_telegram_report(report_text)

    # Завершающее обновление статусного сообщения (если запускалось по запросу)
    if chat_id and message_id:
        if trigger_aggregation:
            finish_msg = (
                f"🍇 <b>[ФЕРГАНСКАЯ ДОЛИНА] Сбор завершен!</b>\n\n"
                f"📁 Успешно скачано: <b>{len(uploaded_ids)} из {total_channels}</b> оптовиков.\n"
                f"🚀 Запущена сборка сводного прайса."
            )
        else:
            finish_msg = (
                f"🍇 <b>[ФЕРГАНСКАЯ ДОЛИНА] Скачивание завершено!</b>\n\n"
                f"📁 Успешно сохранено: <b>{len(uploaded_ids)} из {total_channels}</b> оптовиков в папку <code>fergana</code>.\n"
                f"ℹ️ Для построения сводного прайса отправьте /just_collect_fergana."
            )
        await edit_progress_message(chat_id, message_id, finish_msg)

    return success, len(uploaded_ids)
