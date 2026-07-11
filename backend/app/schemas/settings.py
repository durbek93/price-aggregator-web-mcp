# -*- coding: utf-8 -*-
from typing import Dict, List
from pydantic import BaseModel

class UserSettingsSchema(BaseModel):
    columns: Dict[str, List[str]]
    producers: List[str]
    use_catalog_matching: bool
    legacy_priority_rules: bool
    clear_inputs_after_processing: bool

    class Config:
        from_attributes = True
