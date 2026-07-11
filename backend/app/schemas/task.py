# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

class TaskRecordSchema(BaseModel):
    id: int
    task_type: str
    status: str
    progress_message: Optional[str] = None
    result_file_path: Optional[str] = None
    is_automated: bool = False
    file_ids: Optional[List[int]] = None
    created_at: datetime

    class Config:
        from_attributes = True

class TaskCreateSchema(BaseModel):
    task_type: str
    is_automated: Optional[bool] = False
    file_ids: Optional[List[int]] = None
