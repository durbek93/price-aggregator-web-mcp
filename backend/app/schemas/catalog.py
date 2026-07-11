# -*- coding: utf-8 -*-
from typing import List, Optional
from pydantic import BaseModel

class CatalogItemSchema(BaseModel):
    id: Optional[int] = None
    canonical: str
    aliases: List[str]

    class Config:
        from_attributes = True

class SynonymSuggestionSchema(BaseModel):
    suggested_alias: str
    canonical_id: int
    canonical_name: str
    confidence_score: float

    class Config:
        from_attributes = True
