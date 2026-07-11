# -*- coding: utf-8 -*-
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres_secure_password@db:5432/price_aggregator"
    REDIS_URL: str = "redis://redis:6379/0"
    TELEGRAM_BOT_TOKEN: str = "placeholder_token"
    ALLOWED_TELEGRAM_IDS: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    JWT_SECRET: str = "super_secret_jwt_key_12345"
    INTERNAL_API_KEY: str = "internal_secret_api_key_98765"
    TELEGRAM_GROUP_ID: str = ""
    
    # Filesystem directories
    UPLOAD_DIR: Path = Path("/app/data/uploads")
    OUTPUT_DIR: Path = Path("/app/data/outputs")
    
    @property
    def allowed_telegram_ids_set(self) -> set[int]:
        if not self.ALLOWED_TELEGRAM_IDS.strip():
            return set()
        result = set()
        for x in self.ALLOWED_TELEGRAM_IDS.split(","):
            part = x.strip()
            if part.isdigit():
                result.add(int(part))
        return result

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
