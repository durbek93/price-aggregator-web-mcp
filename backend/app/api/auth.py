# -*- coding: utf-8 -*-
import jwt
from datetime import datetime, timedelta
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import User
from app.schemas import UserSchema
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/verify", response_model=Dict[str, Any])
def verify_magic_token(token: str, db: Session = Depends(get_db)):
    """Проверяет JWT токен из Magic Link и выдает сессионный токен."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Генерируем новый токен для длительной сессии в браузере (на 30 дней)
        session_payload = {
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "exp": datetime.utcnow() + timedelta(days=30)
        }
        session_token = jwt.encode(session_payload, settings.JWT_SECRET, algorithm="HS256")
        
        return {
            "token": session_token,
            "user": {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name
            }
        }
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Неверная или устаревшая ссылка авторизации")


@router.get("/me", response_model=UserSchema)
def get_me(current_user: User = Depends(get_current_user)):
    """Возвращает информацию о текущем авторизованном пользователе."""
    return current_user
