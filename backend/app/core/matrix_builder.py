# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.core.excel_reader import pick_column, resolve_price_column_for_sheet
from app.core.grouping import (
    is_excluded_product,
    normalize_product_for_grouping,
    is_materia_producer_norm,
    match_canonical,
    friendly_source_label,
)
from app.core.price_utils import normalize_name, to_number, round_price


def extract_by_producer(
    df: pd.DataFrame,
    path: Path,
    producer_substrings: List[str],
    key_candidates: List[str],
    name_candidates: List[str],
    price_candidates: List[str],
    stock_candidates: List[str],
    producer_candidates: List[str],
) -> List[Dict[str, Any]]:
    """Извлекает строки, где производитель совпадает с одним из producer_substrings."""
    key_col = pick_column(list(df.columns), key_candidates)
    name_col = pick_column(list(df.columns), name_candidates)
    price_col = resolve_price_column_for_sheet(df, path, price_candidates)
    producer_col = pick_column(list(df.columns), producer_candidates)
    if not name_col or not price_col:
        raise ValueError(f"Не нашёл колонку наименования или цены в файле: {path}")
    rows = []
    for _, r in df.iterrows():
        name_val = r.get(name_col)
        if name_val is None or (isinstance(name_val, float) and pd.isna(name_val)):
            continue
        if is_excluded_product(str(name_val)):
            continue
        producer_val = r.get(producer_col) if producer_col else ""
        prod_norm = normalize_name(str(producer_val or ""))
        if not any(s.lower() in prod_norm for s in producer_substrings):
            continue
        price = to_number(r.get(price_col))
        rounded_price = round_price(price)
        if rounded_price is None:
            continue
        rows.append({
            "key": r.get(key_col),
            "name": name_val,
            "price": rounded_price,
            "producer": producer_val,
            "source": path.stem,
        })
    return rows


def extract_materia_any(
    df: pd.DataFrame,
    path: Path,
    key_candidates: List[str],
    name_candidates: List[str],
    price_candidates: List[str],
    stock_candidates: List[str],
    producer_candidates: List[str],
    catalog: List[Tuple[str, List[str]]],
    *,
    source_label: Optional[str] = None,
    producer_substrings: Optional[List[str]] = None,
    legacy_priority_rules: bool = True,
) -> List[Dict[str, Any]]:
    """Извлекает строки для матрицы: по производителю И/ИЛИ по каталогу."""
    name_col = pick_column(list(df.columns), name_candidates)
    price_col = resolve_price_column_for_sheet(df, path, price_candidates)
    producer_col = pick_column(list(df.columns), producer_candidates)
    key_col = pick_column(list(df.columns), key_candidates)
    if not name_col or not price_col:
        raise ValueError(f"Не нашёл колонку наименования или цены в файле: {path}")
    rows = []
    for _, r in df.iterrows():
        name_val = r.get(name_col)
        if name_val is None or (isinstance(name_val, float) and pd.isna(name_val)):
            continue
        if is_excluded_product(str(name_val)):
            continue
        name_norm = normalize_name(str(name_val))
        producer_val = r.get(producer_col) if producer_col else ""
        prod_norm = normalize_name(str(producer_val or ""))
        if producer_substrings is None:
            by_producer = is_materia_producer_norm(prod_norm)
        else:
            subs = [normalize_name(s) for s in producer_substrings if str(s).strip()]
            by_producer = any(s and s in prod_norm for s in subs)
        canonical = match_canonical(
            name_norm, catalog, legacy_priority_rules=legacy_priority_rules
        )
        if not by_producer and not canonical:
            continue
        price = to_number(r.get(price_col))
        rounded_price = round_price(price)
        if rounded_price is None:
            continue
        canon_value: str
        if canonical:
            canon_value = canonical
        elif catalog:
            canon_value = str(name_val)
        else:
            canon_value = normalize_product_for_grouping(str(name_val))

        row: Dict[str, Any] = {
            "key": r.get(key_col),
            "name": name_val,
            "price": rounded_price,
            "producer": producer_val,
            "source": path.stem,
            "canonical": canon_value,
            "canonical_display": str(name_val).strip(),
        }
        if source_label:
            row["source_label"] = source_label.strip()
        rows.append(row)
    return rows


def build_matrix_from_extracted(
    extracted: List[Dict[str, Any]],
    catalog: List[Tuple[str, List[str]]],
    all_source_labels: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Строит матрицу: строки — канонические препараты, столбцы — дистрибьюторы."""
    canon_order = [c[0] for c in catalog]
    by_canon: Dict[str, Dict[str, Optional[float]]] = {c: {} for c in canon_order}
    display_by_canon: Dict[str, str] = {c: c for c in canon_order}
    sources_seen = set()
    for row in extracted:
        canon = row.get("canonical") or row.get("name")
        if isinstance(canon, str) and canon not in by_canon:
            by_canon[canon] = {}
        if isinstance(canon, str):
            disp = str(row.get("canonical_display") or canon).strip()
            if disp and canon not in display_by_canon:
                display_by_canon[canon] = disp
        if isinstance(canon, str):
            src = row.get("source_label") or friendly_source_label(row["source"])
            sources_seen.add(src)
            price = row.get("price")
            prev_price = by_canon[canon].get(src)
            if prev_price is None:
                by_canon[canon][src] = price
            elif price is not None:
                by_canon[canon][src] = min(prev_price, price)
    if all_source_labels:
        cols = ["Препарат"] + list(all_source_labels)
    else:
        cols = ["Препарат"] + sorted(sources_seen)
    dynamic_canons = [c for c in by_canon.keys() if c not in canon_order]
    if dynamic_canons:
        dynamic_canons.sort(key=lambda x: display_by_canon.get(x, x).casefold())
    final_order = canon_order + dynamic_canons
    data = []
    for canon in final_order:
        d = by_canon.get(canon, {})
        label = display_by_canon.get(canon, canon)
        row = [label] + [d.get(c) for c in cols[1:]]
        data.append(row)
    return pd.DataFrame(data, columns=cols)
