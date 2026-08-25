# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.config import settings
from app.api import router as api_router

# Create database tables if they don't exist
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Error creating database tables: {e}")

# Reset stale tasks on startup
try:
    from app.database import SessionLocal
    from app.models import TaskRecord
    db = SessionLocal()
    stale_tasks = db.query(TaskRecord).filter(TaskRecord.status.in_(["running", "pending"])).all()
    for t in stale_tasks:
        t.status = "failed"
        t.progress_message = "Задача прервана из-за перезапуска сервера."
    db.commit()
    db.close()
    print(f"Reset {len(stale_tasks)} stale tasks on startup.")
except Exception as e:
    print(f"Error resetting stale tasks on startup: {e}")

app = FastAPI(
    title="Price Aggregator Web API",
    version="1.0.0",
    description="Backend API for Price Aggregator Web & Telegram Bot"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class LimitUploadSizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_upload_size: int):
        super().__init__(app)
        self.max_upload_size = max_upload_size

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and "multipart/form-data" in request.headers.get("content-type", ""):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_upload_size:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Размер файла превышает лимит в 50МБ"}
                )
        return await call_next(request)

app.add_middleware(LimitUploadSizeMiddleware, max_upload_size=50 * 1024 * 1024)

app.include_router(api_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to Price Aggregator Web API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

