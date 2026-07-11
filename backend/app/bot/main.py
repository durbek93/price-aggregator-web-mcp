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

async def main() -> None:
    try:
        # Initialize Bot instance with default ParseMode
        bot = Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
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
