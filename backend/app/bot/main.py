# -*- coding: utf-8 -*-
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.bot.middlewares import AccessMiddleware
from app.bot.handlers import router as handlers_router

# Set up logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Initialize dispatcher
dp = Dispatcher()
dp.message.outer_middleware(AccessMiddleware())
dp.callback_query.outer_middleware(AccessMiddleware())

# Register handlers router
dp.include_router(handlers_router)

from aiogram.types import BotCommand

async def main() -> None:
    try:
        # Initialize Bot instance with default ParseMode
        bot = Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
        # Set bot command suggestions in Telegram
        try:
            await bot.set_my_commands([
                BotCommand(command="collect", description="Полный сбор прайсов и построение сводного"),
                BotCommand(command="just_collect", description="Быстрая сборка сводного из сохраненных файлов"),
                BotCommand(command="fetch", description="Скачать свежие прайсы без сборки сводного"),
                BotCommand(command="clean", description="Очистить файлы за период (напр. /clean 05.2026)"),
                BotCommand(command="menu", description="Главное меню аналитики"),
                BotCommand(command="link", description="Ссылка для входа в веб-панель"),
            ])
            logger.info("Bot commands registered successfully.")
        except Exception as e:
            logger.warning(f"Failed to set bot commands: {e}")
        
        # Run bot polling
        logger.info("Starting Telegram Bot (aiogram v3)...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Failed to initialize Telegram Bot: {e}")
        logger.error("Please configure a valid TELEGRAM_BOT_TOKEN in .env and restart this container.")
        # Sleep to keep the container running but idle, preventing Docker from spamming restart logs
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
