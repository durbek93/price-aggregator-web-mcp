import logging
import jwt
import redis
from datetime import datetime, timedelta
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import User
from app.schemas import UserSchema
from app.api.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

def _get_redis():
    try:
        return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning(f"Could not connect to Redis for token invalidation check: {e}")
        return None

@router.get("/verify", response_model=Dict[str, Any])
def verify_magic_token(request: Request, token: str, db: Session = Depends(get_db)):
    """Проверяет одноразовый JWT токен из Magic Link и выдает сессионный токен с защитой от брутфорса."""
    # Защита от брутфорса и сканирования (Rate Limiting: максимум 15 запросов в минуту на IP)
    client_ip = request.client.host if request.client else "unknown"
    r = _get_redis()
    if r:
        ip_limit_key = f"rate_limit:verify:{client_ip}"
        try:
            req_count = r.incr(ip_limit_key)
            if req_count == 1:
                r.expire(ip_limit_key, 60)
            if req_count > 15:
                raise HTTPException(
                    status_code=429,
                    detail="Слишком много попыток авторизации. Пожалуйста, подождите минуту."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis rate limit check error: {e}")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        token_type = payload.get("type")
        if token_type and token_type != "magic_link":
            raise HTTPException(status_code=400, detail="Неверный тип токена")

        jti = payload.get("jti")
        if jti:
            r = _get_redis()
            if r:
                # Атомарная проверка одноразовости (NX = set if Not eXists)
                key = f"magic_used:{jti}"
                is_first_use = r.set(key, "used", ex=900, nx=True)
                if not is_first_use:
                    raise HTTPException(status_code=400, detail="Эта ссылка авторизации уже была использована")

        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Генерируем новый токен для длительной сессии в браузере (на 30 дней)
        session_payload = {
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "type": "session",
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
    except HTTPException:
        raise
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Неверная или устаревшая ссылка авторизации")


@router.get("/me", response_model=UserSchema)
def get_me(current_user: User = Depends(get_current_user)):
    """Возвращает информацию о текущем авторизованном пользователе."""
    return current_user
