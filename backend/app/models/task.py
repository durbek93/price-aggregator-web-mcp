# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    
    # 'svodny_horizontal', 'svodny_vertical', 'assortment', 'cheapest', 'best_suppliers'
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # 'pending', 'running', 'completed', 'failed'
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    progress_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    result_file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_automated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    file_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="tasks")
