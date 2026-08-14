# -*- coding: utf-8 -*-
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import settings

logger = logging.getLogger(__name__)

class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        allowed_ids = settings.allowed_telegram_ids_set
        user = data.get("event_from_user")
        user_id = user.id if user else None
        
        logger.info(f"[AccessCheck] Event type: {type(event).__name__}, User ID: {user_id}, Allowed IDs: {allowed_ids}")

        if not allowed_ids:
            logger.warning(f"[AccessCheck] ALLOWED_TELEGRAM_IDS is empty or not configured. Access denied for user ID: {user_id} (Fail-Closed)")
            return

        if not user or user.id not in allowed_ids:
            logger.warning(f"[AccessCheck] Access denied for unauthorized user ID: {user_id}")
            return

        logger.info(f"[AccessCheck] Access granted for user ID: {user_id}")
        return await handler(event, data)
