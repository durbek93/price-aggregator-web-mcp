# -*- coding: utf-8 -*-
from typing import Optional
from pydantic import BaseModel

class UserSchema(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None

    class Config:
        from_attributes = True
