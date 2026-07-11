# -*- coding: utf-8 -*-
import logging
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatAction

import config
from backend_client import (
    fetch_analysis_data,
    fetch_manufacturer_data,
    fetch_drug_data,
)
from gemini_service import (
    classify_user_request,
    generate_ai_report,
    generate_manufacturer_report,
    generate_drug_report,
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


@dp.message()
async def handle_new_report_notification(message: types.Message):
    """Обрабатывает сообщения в закрытой группе и реагирует на уведомления от главного бота."""
    chat_id = message.chat.id
    
    # 1. Проверяем ID группы (если настроен)
    if config.TELEGRAM_GROUP_ID and chat_id != config.TELEGRAM_GROUP_ID:
        return
        
    # 2. Проверяем отправителя (сообщение должно быть от главного бота или содержать упоминание)
    text = message.text or message.caption or ""
    text_low = text.lower()
    
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
        
    # 4. Проверяем триггерный текст от бэкенда или ключевые слова
    has_trigger_keyword = any(
        kw in text_low
        for kw in [
            "сводный прайс-лист собран автоматически",
            "отчет",
            "анализ",
            "изменени",
            "дефицит",
            "аналитик",
        ]
    )
    if not has_trigger_keyword:
        logger.info("Ignored message: no trigger keyword found in message.")
        return
        
    logger.info("Valid trigger message intercepted. Processing analysis report...")
    
    # Отправляем статус "печать"
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    
    # Классифицируем запрос
    classification = await classify_user_request(text)
    req_type = classification.get("request_type")
    target = classification.get("target")
    days = classification.get("days", 3)
    
    if req_type == "manufacturer" and target:
        logger.info(f"Classified as manufacturer request: {target} for {days} days")
        
        # Шаг 1: Запрашиваем исторические данные по производителю
        data = await fetch_manufacturer_data(target, days)
        if not data:
            await message.reply(f"❌ Не удалось получить данные о ценах для производителя {target} за последние {days} дней.")
            return
            
        if not data.get("drugs"):
            await message.reply(f"⚠️ Данные о ценах препаратов производителя {target} за последние {days} дней отсутствуют.")
            return
            
        # Шаг 2: Генерируем специализированный отчет
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            report_text = await generate_manufacturer_report(data, target, days)
        except Exception as e:
            logger.exception(f"Failed to generate manufacturer report: {e}")
            await message.reply(f"❌ Ошибка генерации отчета нейросетью: {str(e)}")
            return
            
        # Шаг 3: Публикуем отчет в чат
        try:
            logger.info("Sending manufacturer analytical report...")
            await message.reply(report_text, parse_mode="HTML")
        except Exception as parse_err:
            logger.warning(f"Failed to send HTML: {parse_err}. Retrying as plain text...")
            await message.reply(report_text)
            
        return

    elif req_type == "drug" and target:
        logger.info(f"Classified as drug request: {target} for {days} days")
        
        # Шаг 1: Запрашиваем исторические данные по препарату
        data = await fetch_drug_data(target, days)
        if not data:
            await message.reply(f"❌ Не удалось получить данные о ценах для препарата «{target}» за последние {days} дней.")
            return
            
        if not data.get("drugs"):
            await message.reply(f"⚠️ Данные о ценах для препарата «{target}» за последние {days} дней отсутствуют.")
            return
            
        # Шаг 2: Генерируем специализированный отчет
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            report_text = await generate_drug_report(data, target, days)
        except Exception as e:
            logger.exception(f"Failed to generate drug report: {e}")
            await message.reply(f"❌ Ошибка генерации отчета по препарату: {str(e)}")
            return
            
        # Шаг 3: Публикуем отчет в чат
        try:
            logger.info("Sending drug analytical report...")
            await message.reply(report_text, parse_mode="HTML")
        except Exception as parse_err:
            logger.warning(f"Failed to send HTML: {parse_err}. Retrying as plain text...")
            await message.reply(report_text)
            
        return

    # Шаг 1: Запрашиваем дельту цен с бэкенда для общего отчета
    data = await fetch_analysis_data()
    if not data:
        await message.reply("❌ Не удалось получить данные анализа цен от бэкенда.")
        return
        
    # Проверим, есть ли вообще данные по препаратам
    if not data.get("drugs"):
        await message.reply("⚠️ Бэкенд не вернул данных о ценах препаратов для анализа (список пуст).")
        return
    
    # Проверяем, запрашивает ли пользователь отчет с дефицитом
    include_deficit = "дефицит" in text_low
    logger.info(f"Generating report with include_deficit={include_deficit}")
    
    # Шаг 2: Генерируем аналитику через Gemini 2.5 Flash
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    try:
        report_text = await generate_ai_report(data, include_deficit=include_deficit)
    except Exception as e:
        logger.exception(f"Failed to generate Gemini report: {e}")
        await message.reply(f"❌ Ошибка генерации отчета нейросетью: {str(e)}")
        return
        
    # Шаг 3: Публикуем отчет в чат группы ответом на исходное сообщение
    try:
        logger.info("Sending analytical report to the group chat...")
        await message.reply(report_text, parse_mode="HTML")
    except Exception as parse_err:
        logger.warning(
            f"Failed to send message in HTML parse mode: {parse_err}. Retrying as plain text..."
        )
        await message.reply(report_text)


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
