# -*- coding: utf-8 -*-
"""Общие утилиты для нормализации текста, преобразования типов и работы с колонками Excel."""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, List, Optional
import pandas as pd

_STAR_MARKERS_RE = re.compile(r"[\*＊⁎∗⋆]+")
_TM_RE = re.compile(r"[®™©]+")


def strip_star_markers(s: str) -> str:
    """Убирает звездочки разных начертаний."""
    if not isinstance(s, str):
        return ""
    return _STAR_MARKERS_RE.sub("", s)


def strip_trademark_symbols(s: str) -> str:
    """Убирает символы торговых марок."""
    if not isinstance(s, str):
        return ""
    return _TM_RE.sub("", s)


def normalize_text(value: Any) -> str:
    """Для сравнения ячеек и препаратов; убирает *** и аналоги из прайсов (напр. Верона)."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = strip_star_markers(s)
    return strip_trademark_symbols(s)


def normalize_name(s: str) -> str:
    """Нормализация наименования для сопоставления с каталогом."""
    if not s or not isinstance(s, str):
        return ""
    return " ".join(str(s).lower().split())


def to_number(value: Any) -> Optional[float]:
    """Безопасное приведение значения ячейки к числу с плавающей точкой, убирая пробелы и валюты."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    for ch in ["₽", "руб", "руб.", "сум"]:
        text = text.replace(ch, "")
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def round_price(value: Any) -> Optional[int]:
    """Округляет цену до целого по правилу .5 вверх (ROUND_HALF_UP)."""
    if value is None:
        return None
    try:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return None


def find_column_index(headers: List[object], candidates: List[str]) -> Optional[int]:
    """Находит 1-based индекс колонки среди заголовков, сопоставляя нормализованный текст."""
    by_norm = {normalize_text(header): idx for idx, header in enumerate(headers, start=1)}
    for cand in candidates:
        idx = by_norm.get(normalize_text(cand))
        if idx is not None:
            return idx
    return None
