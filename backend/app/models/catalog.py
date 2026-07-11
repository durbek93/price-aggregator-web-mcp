# -*- coding: utf-8 -*-
from typing import List
from sqlalchemy import Integer, String, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class CatalogItem(Base):
    __tablename__ = "catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    canonical: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # List of aliases (stored as JSON array)
    aliases: Mapped[List[str]] = mapped_column(JSON, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="catalog_items")
