# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz

from app.core.price_utils import (
    normalize_name,
    strip_star_markers,
    strip_trademark_symbols,
)

# Суффиксы источника/производителя, которые встречаются в конце названия
_SOURCE_SUFFIX_RE = re.compile(
    r"[/\\]\s*(?:мат\.?\s*мед\.?|мат\.?медика?|materia?|mm|мм)\s*$",
    re.IGNORECASE,
)

# Таблица нормализации фармацевтических форм выпуска
_FORM_NORMALIZATION: List[Tuple[str, str]] = [
    (r"\bгранул[аыь]?\b", "гран"),
    (r"\bгран\b", "гран"),
    (r"\bтаблетк[аи]\b", "таб"),
    (r"\bтабле\b", "таб"),
    (r"\bтабл\b", "таб"),
    (r"\bтаб\b", "таб"),
    (r"\bкапсул[аы]?\b", "кап"),
    (r"\bкапс\b", "кап"),
    (r"\bкап\b", "кап"),
    (r"\bпастилк[аи]\b", "паст"),
    (r"\bпаст\b", "паст"),
    (r"\bграмм[а]?\b", "г"),
    (r"\bмиллиграм[м]?[а]?\b", "мг"),
    (r"\bштук[аи]?\b", "шт"),
    (r"\bшт\b", "шт"),
]

# Исключения для склейки слов
_NO_JOIN_TOKENS = frozenset(
    {
        "мг",
        "мл",
        "me",
        "таб",
        "кап",
        "спрей",
        "паст",
        "паста",
        "доз",
        "доза",
        "инъек",
        "для",
        "г",
        "дети",
        "взросл",
        "эвкалипт",
        "н",
    }
)


def _join_adjacent_cyrillic_name_parts(s: str) -> str:
    parts = s.split()
    if len(parts) < 2:
        return s
    out: List[str] = []
    i = 0
    while i < len(parts):
        a = parts[i]
        b = parts[i + 1] if i + 1 < len(parts) else None
        if (
            b is not None
            and re.fullmatch(r"[а-яё]{2,14}", a)
            and re.fullmatch(r"[а-яё]{2,14}", b)
            and len(a) <= 7
            and len(b) <= 7
            and len(a) + len(b) <= 11
            and a.casefold() not in _NO_JOIN_TOKENS
            and b.casefold() not in _NO_JOIN_TOKENS
        ):
            out.append(a + b)
            i += 2
        else:
            out.append(a)
            i += 1
    return " ".join(out)


def normalize_product_for_grouping(raw: str) -> str:
    """
    Нормализация названия для ключа группировки в сводном.
    Убирает типичные отличия между прайсами: звёздочки, скобки, пробелы в дозах, таб/табл., D/Д и т.д.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).replace("\r", " ").replace("\n", " ")
    s = unicodedata.normalize("NFKC", s)
    s = _SOURCE_SUFFIX_RE.sub("", s).strip()
    s = normalize_name(s)
    s = strip_star_markers(s)
    s = strip_trademark_symbols(s)
    s = s.replace("+", " ")
    s = re.sub(r"\bдоза\b", "доз", s)
    s = re.sub(r"\bд/взрос\w*\b", "взросл ", s)
    s = re.sub(r"\bвзрос\w*\b", "взросл ", s)
    s = re.sub(r"\bд/дет\w*\b", "дети ", s)
    s = re.sub(r"\bдетс\w*\b", "дети ", s)
    s = re.sub(r"\bдетей\b", "дети ", s)
    s = re.sub(r"\bэвкалипт\w*", "эвкалипт ", s)
    s = _join_adjacent_cyrillic_name_parts(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("/", " ")
    s = re.sub(r"(\d)[.,](\d+)", r"\1d\2", s)
    if re.search(r"0d1", s):
        s = re.sub(r"(?:5мг|5\s+мг)\s+", "", s, count=1)
    if re.search(r"0d05", s):
        s = re.sub(r"(?:5мг|5\s+мг)\s+", "", s, count=1)
    s = re.sub(r"\[[^]]{0,120}]", " ", s)
    s = re.sub(r"\([^)]{0,120}\)", " ", s)
    s = re.sub(r"\bвитамин\s+d\s*3\b", "витамин д3 ", s)
    s = re.sub(r"\bвитамин\s+д\s*3\b", "витамин д3 ", s)
    s = re.sub(r"витаминд3\b", "витамин д3", s)
    s = re.sub(r"(\d+)\s*(ме|me)\b", r"\1 me", s, flags=re.IGNORECASE)
    s = re.sub(r"\bh\s*(\d+)", r" \1 ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bн\s*(\d+)", r" \1 ", s)
    s = re.sub(r"\bh(\d+)", r" \1 ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bн(\d+)", r" \1 ", s)
    s = re.sub(r"\bkrka\b", " ", s)
    s = re.sub(r"-к\b", " ", s)
    s = re.sub(r"\bп\s*/\s*о\b", " ", s)
    s = s.replace("№", " n")
    s = re.sub(r"\bno\s*(\d)", r"n\1", s)
    s = re.sub(r"\bамп\.?\b", "инъек ", s)
    s = re.sub(r"\bр-р\b", "инъек ", s)
    s = re.sub(r"\bд/ин\.?\b", "инъек ", s)
    s = re.sub(r"\bд/пр\.?\b", "инъек ", s)
    
    for pattern, replacement in _FORM_NORMALIZATION:
        s = re.sub(pattern, replacement + " ", s)
    s = re.sub(r"\bгомеоп\w*\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"(\d)([а-яёa-z])", r"\1 \2", s, flags=re.IGNORECASE)
    s = re.sub(r"([а-яёa-z])(\d)", r"\1 \2", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\d\sd\u0400-\u04FFa-z]", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    
    toks = [t for t in s.split() if t]
    if not toks:
        return ""
    toks = [t for t in toks if t.casefold() not in ("н", "h")]
    unit_like = any(
        t.casefold() in ("мг", "мл", "me")
        or t.casefold().endswith("me")
        or ("d" in t and any(c.isdigit() for c in t))
        for t in toks
    )
    if unit_like:
        toks = [t for t in toks if t.casefold() not in ("таб", "гран", "кап", "паст")]
    if any(t.casefold() == "гран" for t in toks):
        toks = [t for t in toks if t.casefold() != "г"]
    
    st = sorted(toks, key=str.casefold)
    deduped: List[str] = []
    for t in st:
        if deduped and deduped[-1].casefold() == t.casefold():
            continue
        deduped.append(t)
    return " ".join(deduped)


def fuzzy_merge_canonicals(
    extracted: List[Dict[str, Any]],
    threshold: int = 88,
    catalog: Optional[List[Tuple[str, List[str]]]] = None,
) -> List[Dict[str, Any]]:
    """Второй проход группировки: объединяет похожие позиции по Union-Find."""
    catalog_canonicals = {c[0] for c in catalog} if catalog else set()
    keys: List[str] = []
    seen: set = set()
    for row in extracted:
        c = row.get("canonical", "")
        if c and c not in seen:
            seen.add(c)
            keys.append(c)

    if len(keys) < 2:
        return extracted

    parent: Dict[str, str] = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        a_is_cat = ra in catalog_canonicals
        b_is_cat = rb in catalog_canonicals
        if a_is_cat and not b_is_cat:
            parent[rb] = ra
        elif b_is_cat and not a_is_cat:
            parent[ra] = rb
        else:
            if len(ra) > len(rb) or (len(ra) == len(rb) and ra > rb):
                ra, rb = rb, ra
            parent[rb] = ra

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            norm_a = normalize_product_for_grouping(a)
            norm_b = normalize_product_for_grouping(b)
            
            toks_a = a.split()
            toks_b = b.split()
            first_a = next((t for t in toks_a if not t.isdigit() and t != "n"), "")
            first_b = next((t for t in toks_b if not t.isdigit() and t != "n"), "")
            if first_a.casefold() != first_b.casefold():
                continue
                
            def _extract_nums(normalized_str: str) -> frozenset:
                nums = set()
                for t in normalized_str.split():
                    if t.isdigit():
                        nums.add(t)
                    elif "d" in t and any(c.isdigit() for c in t):
                        nums.add(t)
                return frozenset(nums)
                
            nums_a = _extract_nums(norm_a)
            nums_b = _extract_nums(norm_b)
            if nums_a != nums_b:
                continue
                
            score = fuzz.token_sort_ratio(norm_a.lower(), norm_b.lower())
            if score >= threshold:
                union(a, b)

    mapping: Dict[str, str] = {k: find(k) for k in keys}
    for row in extracted:
        c = row.get("canonical", "")
        if c in mapping:
            row["canonical"] = mapping[c]

    return extracted


def is_materia_producer_norm(text_norm: str) -> bool:
    """Проверка, что нормализованный текст относится к производителю Materia Medica."""
    if not text_norm:
        return False
    t = text_norm.replace("-", " ").replace("/", " ")
    if "материа" in t or "материя" in t or "materia" in t:
        return True
    return False


def friendly_source_label(source_stem: str) -> str:
    """Человекочитаемое название дистрибьютора из имени файла."""
    s = source_stem
    mapping = {
        "верона": "Верона",
        "pharma choice": "Фарма Чойз",
        "pharm gate": "Гейт Фарм",
        "фарм гейт": "Гейт Фарм",
        "охотник": "Охотник Фарм",
        "турон": "Турон Фарм",
        "саида": "Саида Фарм",
        "фарма космос": "Фарма Космос",
        "фарма космом": "Фарма Космос",
        "гранд фарм": "Гранд Фарм",
        "аззам": "Аззам Фарм",
        "мерос": "Мерос Фарм",
        "фарм континент": "Фарм Континент",
        "фарм люкс": "Фарм Люкс",
        "гармония": "Гармония Фарм",
        "макро фарм": "Макро Фарм",
        "мемори": "Мемори Фарм",
        "релианс": "Релианс Фарм",
        "универсал ника": "Универсал Ника Фарм",
        "навкирон": "Навкирон Фарм",
        "нам экомед": "Нам экомед фарм",
        "хожи акбар": "Хожи Акбар Фарм",
        "зилол мед": "Зилол Мед",
        "гейт": "Гейт Фарм",
        "Эверест фарм": "Эверест Фарм",
        "Фарм Инвест": "Фарм Инвест",
    }
    lower = s.lower()
    for key, label in mapping.items():
        if key in lower:
            return label
    parts = []
    for p in s.replace(".", " ").replace("_", " ").split():
        if p.isdigit() or (len(p) >= 4 and p[:2].isdigit() and p[2] in ".-"):
            continue
        parts.append(p)
    return " ".join(parts) if parts else s


def build_catalog_materia_medica() -> List[Tuple[str, List[str]]]:
    """Каноническое название + синонимы для матчинга."""
    return [
        ("Анаферон детский таб №20", [
            "анаферон дет", "анаф дет", "анаферон детский таб", "анаферон детский таб n20",
            "анаферон детский таб. №20", "анаферон таб. детские №20", "анаферон таб. детск. №20",
            "анаферон таб детск", "анаферон таб детские n20",
        ]),
        ("Анаферон взрослый таб №20", ["Анаферон взрос. №20", "АНАФЕРОН №20 Д/ВЗР", "Анаферон таб. Взр №20", "анаферон таб", "Анаферон взр таб №20 !!!", "Анаферон взр таб №20", "анаферон взрослый", "анаферон таб. №20", "АНАФЕРОН ДЛЯ ВЗРОС  ТАБ N20", "анаферон для взрос", "анаферон для взрослых", "анаферон взр таб n20"]),
        ("Анаферон капли (детские) 25мл", [
            "Анаферон детский капли 25мл.", "Анаферон детск капли для п/внутрь 25мл гомеоп", "Анаферон детский капли 25мл", "Анаферон детский капли гомеоп. д/приема внутрь 25мл ", "Анаферон детский капли д/приема внутрь 25мл", "анаферон капли", "анаферон капли дет", "анаферон капли 25", "анаферон капли (детские) 25мл",
            "анаферон детский капли", "анаферон капли д/детей 25мл", "Анаферон Детский капли 25мл", "Анаферон детский капли д/детей 25мл", "Анаферон детский  капли для п/внутрь 25мл", "Анаферон детский капли д/п/внутрь 25мл"    
        ]),
        ("Эргоферон таб №20", ["эргоферон таб", "эргоферон таб. №20"]),
        ("Ренгалин таб. №20", ["ренгалин таб", "ренгалин таб. №20",]),
        ("Ренгалин раствор №1", ["Ренгалин р-р д/внутр. прим.100мл", "Ренгалин р-р. 100мл №1", "Ренгалин р-р для прием.внутрь гомеоп. 100мл", "Ренгалин р-р д/приёма внутрь 100мл ", "Ренгалин р-р 100мл №1", "ренгалин раствор","РЕНГАЛИН Р-Р Д/ПРИЕМА ВНУТРЬ ГОМЕО-Е 100МЛ", 
            "Ренгалин р-р д/пр внут гомеоп  100мл", "ренгалин 100", "ренгалин сироп", "Ренгалин р-р д/прием. внутрь 100мл", "Ренгалин р-р д/пр внут 100мл", "Ренгалин р-р д/пр. внутрь гомеоп. 100мл", "Ренгалин р-р. 100мл №1"]),
        ("Тенотен таб №40", [
            "тенотен таб. №40", "тенотен таб n40", "ТЕНОТЕН ВЗРОС  ТАБ N40",
            "тенотен взр таб", "тенотен взр", "тенотен взрос",
            "тенотен таб. д/рассас", "тенотен таб д/рассас", "тенотен таб д рассас",
        ]),
        ("Тенотен детский таб №40", [
            "Тенотен-Детский таб.№40", "тенотен дет", "тенотен таб детский", "тенотен таб. детский №40",
            "тенотен таб №40 д/детей", "тенотен таб. детс. №40", "Тенотен таб. детский №40",
        ]),
        ("Импаза №20", ["ИМПАЗА №20", "импаза таб", "импаза таб. №20"]),
        ("Афала №100", [
            "афала №100", "афала таб №100", "афала таб. №100", "афала таб n100",
            "афала гомеопат таб n100", "афала гомеопат таб №100",
        ]),
        ("Афалаза", ["афалаза"]),
        ("Климаксан таб. №20", ["климаксан таб", "климаксан таб. №20"]),
        ("Климаксан гранулы 10г", ["климаксан гранулы", "климаксан 10г гранул", "климаксан 10г гранул/мат.мед", "климаксан гран"]),
        ("Млекоин гранулы 10г", ["млекоин гранулы", "млекоин 10г", "МЛЕКОИН ГРАН.ГОМЕОП.10Г"]),
        ("Диваза", ["диваза"]),
        ("Успокой", ["успокой"]),
        ("Фарингомед", ["фарингомед"]),
    ]


def match_canonical(
    name_norm: str,
    catalog: List[Tuple[str, List[str]]],
    *,
    legacy_priority_rules: bool = True,
) -> Optional[str]:
    """По нормализованному названию возвращает каноническое или None."""
    if legacy_priority_rules:
        if "анаферон" in name_norm:
            if ("капл" in name_norm) or ("25мл" in name_norm):
                return "Анаферон капли (детские) 25мл"
            if ("взрос" in name_norm) or ("для взрос" in name_norm) or ("д/взр" in name_norm):
                return "Анаферон взрослый таб №20"
            if "дет" in name_norm:
                return "Анаферон детский таб №20"
            return "Анаферон взрослый таб №20"

        if "тенотен" in name_norm:
            if ("дет" in name_norm) or ("д/дет" in name_norm):
                return "Тенотен детский таб №40"
            if ("взр" in name_norm) or ("взрос" in name_norm):
                return "Тенотен таб №40"

        if "климаксан" in name_norm:
            if "таб" in name_norm:
                return "Климаксан таб. №20"
            if "гран" in name_norm or "гранул" in name_norm:
                return "Климаксан гранулы 10г"

        if re.search(r"\bдуафа", name_norm):
            return None

    for canonical, aliases in catalog:
        for alias in aliases:
            alias_norm = normalize_name(alias)
            if not alias_norm:
                continue
            if alias_norm in name_norm:
                return canonical
            if fuzz.ratio(name_norm, alias_norm) >= 90 and name_norm[:5] == alias_norm[:5]:
                return canonical
        if normalize_name(canonical) in name_norm:
            return canonical
    return None


def is_excluded_product(name: str) -> bool:
    """Проверяет, должен ли товар быть исключен из сводного прайса."""
    if not name:
        return False
    norm_name = " ".join(str(name).lower().split())
    for pattern in [
        "лейкопластырь на тканевой основе 1х250см №1",
        "лейкопластырь на тканевой основе 1х250см n1",
        "лейкопластырь на тканевой основе 1х250 см №1",
        "лейкопластырь на тканевой основе 1х250 см n1",
        "лейкопластырь на тканевой основе 1х500см №1",
        "лейкопластырь на тканевой основе 1х500см n1",
        "лейкопластырь на тканевой основе 1х500 см №1",
        "лейкопластырь на тканевой основе 1х500 см n1",
        "лейкопластырь фикс н/с ролепласт 2х300см №1",
        "лейкопластырь фикс н/с ролепласт 2х300см n1",
        "лейкопластырь фикс н/с ролепласт 2х300 см №1",
        "лейкопластырь фикс н/с ролепласт 2х300 см n1",
    ]:
        if pattern in norm_name:
            return True
    return False
