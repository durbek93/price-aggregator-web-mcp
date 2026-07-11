# -*- coding: utf-8 -*-
from typing import List, Dict
from sqlalchemy import Integer, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # JSON structure for column candidates
    # e.g., {"key_candidates": [...], "name_candidates": [...]}
    columns: Mapped[Dict[str, List[str]]] = mapped_column(JSON, nullable=False)
    
    # List of producer names to filter (stored as JSON array)
    producers: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    
    use_catalog_matching: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legacy_priority_rules: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    clear_inputs_after_processing: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="settings")
