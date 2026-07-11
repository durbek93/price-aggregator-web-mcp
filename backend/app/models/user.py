# -*- coding: utf-8 -*-
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Integer, BigInteger, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    settings: Mapped["UserSettings"] = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    catalog_items: Mapped[List["CatalogItem"]] = relationship("CatalogItem", back_populates="user", cascade="all, delete-orphan")
    files: Mapped[List["FileRecord"]] = relationship("FileRecord", back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[List["TaskRecord"]] = relationship("TaskRecord", back_populates="user", cascade="all, delete-orphan")
