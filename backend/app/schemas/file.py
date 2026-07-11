# -*- coding: utf-8 -*-
from datetime import datetime
from pydantic import BaseModel

class FileRecordSchema(BaseModel):
    id: int
    filename: str
    display_name: str
    file_type: str
    read_preset: str
    file_size: int
    uploaded_at: datetime

    class Config:
        from_attributes = True

class FileUpdateSchema(BaseModel):
    read_preset: str
