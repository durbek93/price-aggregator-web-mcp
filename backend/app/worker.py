# -*- coding: utf-8 -*-
from celery import Celery
from app.config import settings

celery_app = Celery(
    "price_aggregator_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Celery configuration & hardening
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_time_limit=300,        # Жесткий таймаут 5 минут
    task_soft_time_limit=240,   # Мягкий таймаут 4 минуты
    worker_max_tasks_per_child=50,  # Перезапуск воркера каждые 50 задач против утечек RAM
)

# Autodiscover tasks from app.tasks
celery_app.autodiscover_tasks(["app"])
