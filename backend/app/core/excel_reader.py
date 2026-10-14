# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, List, Optional, Tuple

import openpyxl
import pandas as pd

# --- константы ---
DEFAULT_KEY_CANDIDATES = ["Артикул", "Код", "SKU", "ID", "PartNumber", "НоменклатураКод"]
DEFAULT_NAME_CANDIDATES = [
    "Наименование",
    "Наименование товаров",
    "Наименование товара",
    "Наименование препарата",
    "Наименование препаратов",
    "Наименование медикаментов",
    "Товары",
    "Махсулот номи",
    "Номи",
    "Товар номи",
    "Препарат номи",
    "Махсулот",
    "Номенклатура",
    "Товар",
    "Название",
    "Name",
    "Наимменование",
    "Препарат",
    "Позиция",
]
DEFAULT_PRICE_CANDIDATES = [
    "-4",
    "-4%",
    "Цена -4%",
    "Цена-4%",
    "Цена - 4%",
    "-3",
    "-3%",
    "Цена -3%",
    "Цена-3%",
    "Цена - 3%",
    "-2",
    "-2%",
    "Цена -2%",
    "Цена-2%",
    "Цена - 2%",
    "Цена-4",
    "Цена 4",
    "Цена - 4",
    "Цена -4",
    "Цена-3",
    "Цена 3",
    "Цена - 3",
    "Цена -3",
    "Цена-2",
    "Цена 2",
    "Цена - 2",
    "Цена -2",
    "Цена отпускная под 100%",
    "Цена (100%) с НДС",
    "Цена При 100 % оплате цена",
    "При 100 % оплате цена",
    "Тип цены Сотув",
    "Цена С НДС",
    "Цена 100%",
    "цена 100 %",
    "Цена с НДС 100%",
    "Цена для клиента с предоплатой 100%",
    "Цена с НДС",
    "Цена без НДС",
    "Цена",
    "Цена сум",
    "Цена отпускная под 25%",
    "Цена Спец мин 1млн",
    "Тип цены При 100% Оплате (перечисление)",
    "При 100% Оплате",
    "Цена договорная",
    "Цена (с НДС)",
    "Цена Договорная",
    "Цена переч",
    "Цена переч:",
    "Цена реал",
    "ПриходЦена",
    "Сумма заказ",
    "Сумма",
    "Отп. Цена",
    "Price",
    "Нарх",
    "Нархи",
    "Сотув нархи",
    "100% тўлов",
    "100% тулов",
    "Пул кўчириш",
    "Пул кучириш",
    "Накд",
    "Розница",
    "Опт",
    "Цена опт.",
    "Цена опт",
    "Цена Опт",
    "Цена Опт.",
    "Стоимость",
    "Тариф",
    "Продажная",
    "Продажная цена",
    "Продажная с НДС",
    "Цена прайс",
    "100% цена (Узбекский сум)",
    "100% цена",
    "Цена (Узбекский сум)",
    "Цена со скидкой",
    "Отпускная цена",
    "Отпуск.цена",
    "Отпускная цена с НДС",
    "Отп. цена с НДС",
    "100%",
    "1",
    "1.0",
]
DEFAULT_STOCK_CANDIDATES = ["Остаток", "Наличие", "Stock", "Qty", "Количество", "Кол-во", "Микдор", "Миқдор", "Қолдиқ", "Колдик"]
DEFAULT_PRODUCER_CANDIDATES = ["Производитель", "Бренд", "Manufacturer", "Ишлаб чикарувчи", "Ишлаб чиқарувчи", "Давлат", "Произ.", "Произв.", "Произв", "Произ-ль", "Произв-ль", "Производство", "Завод", "Фирма"]
DEFAULT_EXPIRY_CANDIDATES = ["Срок годности", "Срок", "Годен до", "Expiry", "Муддати"]


def _normalize_col_for_match(col: str) -> str:
    """Нормализация названия колонки для сопоставления с кандидатами."""
    if not isinstance(col, str):
        return ""
    s = " ".join(str(col).replace("\xa0", " ").split())
    # Приводим любые варианты дефисов к стандартному дефису
    for dash in ["–", "—", "−", "‐"]:
        s = s.replace(dash, "-")
    while s and s[-1] in ":;":
        s = s[:-1].strip()
    return s.casefold()


def _clean_col(c: Any) -> str:
    return str(c).strip() if c is not None else ""


def _make_columns_unique(cols: List[Any]) -> List[str]:
    """Дедупликация имен колонок (например: Цена, Цена_1, Цена_2)."""
    seen = {}
    result = []
    for c in cols:
        name = _clean_col(c)
        if not name:
            name = "Unnamed"
        if name in seen:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 0
            result.append(name)
    return result


def pick_column(
    columns: List[str],
    candidates: List[str],
) -> Optional[str]:
    """Выбирает первую колонку из df, нормализованное имя которой совпадает с одним из кандидатов."""
    norm_cols = {_normalize_col_for_match(c): c for c in columns}
    for cand in candidates:
        n = _normalize_col_for_match(cand)
        if n in norm_cols:
            return norm_cols[n]
    return None


def pick_price_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    """
    Выбирает колонку цены:
    1) сначала точное совпадение по candidates;
    2) если найдено несколько, приоритет у колонок с "цена/price/нарх",
       а "сумма" считается менее приоритетной.
    """
    # Исключаем колонки сумм, заказов и НДС
    valid_cols = []
    for c in columns:
        low = str(c).lower().strip()
        if low in ["ндс", "ндс%", "ставка ндс", "ставка ндс, %", "ндс, %", "заказ", "заказы", "кол-во", "кол во", "сумма", "сумма заказа", "сумма заказ", "сумма со скидкой", "sum", "total", "кол-во заказ", "количество"]:
            continue
        if any(x in low for x in ["сумма", "sum", "total"]):
            continue
        valid_cols.append(c)

    norm_cols = {_normalize_col_for_match(c): c for c in valid_cols}
    present = []
    for idx, cand in enumerate(candidates):
        n = _normalize_col_for_match(cand)
        if n in norm_cols:
            present.append((idx, n, norm_cols[n]))
    if not present:
        return None

    def score(name_norm: str, pos: int) -> Tuple[int, int]:
        low = name_norm.lower()
        strong = ("цена" in low) or ("price" in low) or ("нарх" in low)
        weak_sum = "сумма" in low
        return (2 if strong else 0) + (0 if weak_sum else 1), -pos

    best = max(present, key=lambda x: score(x[1], x[0]))
    return best[2]


def load_distributor_rules() -> Dict[str, Any]:
    for p in [Path("/app/data/distributor_rules.json"), Path(__file__).parent.parent.parent / "data" / "distributor_rules.json"]:
        if p.exists():
            try:
                import json
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def resolve_price_column_for_sheet(df: pd.DataFrame, path: Path, price_candidates: List[str]) -> Optional[str]:
    name_low = path.name.lower()
    cols = list(df.columns)
    
    rules = load_distributor_rules()
    for r_k, r_v in rules.items():
        if r_k.lower() in name_low:
            c100 = r_v.get("p100_col")
            if c100:
                for c in cols:
                    if "".join(str(c).lower().split()) == "".join(str(c100).lower().split()):
                        return c
            c25 = r_v.get("p25_col")
            if c25:
                for c in cols:
                    if "".join(str(c).lower().split()) == "".join(str(c25).lower().split()):
                        return c

    if "meros" in name_low or "мерос" in name_low:
        for col in cols:
            c_clean = "".join(str(col).lower().split())
            if any(k in c_clean for k in ["при100%оплате", "цена100%", "100%оплата"]):
                return col
        for col in cols:
            c_clean = "".join(str(col).lower().split())
            if "договорная" in c_clean or "договор" in c_clean:
                return col
        for col in cols:
            c_clean = "".join(str(col).lower().split())
            if c_clean == "цена":
                return col
            
    elif "grand" in name_low or "гранд" in name_low:
        if "100" in name_low:
            for col in cols:
                c_low = str(col).lower().strip()
                if "без ндс" in c_low or "безндс" in c_low:
                    continue
                if "100" in c_low:
                    return col
            # Fallback
            valid_cols = [c for c in cols if "без ндс" not in str(c).lower() and "безндс" not in str(c).lower()]
            return pick_price_column(valid_cols, price_candidates)
        else:
            for col in cols:
                col_clean = " ".join(str(col).lower().split())
                if "без ндс" in col_clean or "безндс" in col_clean:
                    continue
                if any(x in col_clean for x in ["отпускная цена с ндс", "отпуск.цена с ндс", "отпускная цена", "отпуск.цена", "отп. цена", "отп.цена"]):
                    return col
            # Fallback
            valid_cols = [c for c in cols if "без ндс" not in str(c).lower() and "безндс" not in str(c).lower()]
            return pick_price_column(valid_cols, price_candidates)
            
    elif "verona" in name_low or "верона" in name_low:
        # Для Вероны парсим цены ТОЛЬКО 100%
        for col in cols:
            c_clean = "".join(str(col).lower().split())
            if any(k in c_clean for k in ["100%", "100", "при100%", "предоплата100%", "цена100%"]):
                return col
        return pick_price_column(cols, price_candidates)

    elif "azzam" in name_low or "аззам" in name_low:
        # Для Аззам парсим цены БЕЗ 100%
        non_100_cols = [c for c in cols if not any(k in "".join(str(c).lower().split()) for k in ["100%", "100"])]
        if non_100_cols:
            return pick_price_column(non_100_cols, price_candidates)
        return pick_price_column(cols, price_candidates)

    elif "luxe" in name_low or "люкс" in name_low:
        return pick_price_column(cols, price_candidates)

    elif "khoji" in name_low or "хожи" in name_low:
        for col in cols:
            c_clean = "".join(str(col).lower().split())
            if any(k in c_clean for k in ["ценасндс", "цена", "нарх"]):
                return col
        return pick_price_column(cols, price_candidates)
        
    elif "biotek" in name_low or "биотек" in name_low:
        found_col = None
        # First check for explicit columns like Цена-4, Цена 4, -4, Цена-3, Цена 3, -3
        target_names = ["цена-4", "цена 4", "цена - 4", "-4", "цена-3", "цена 3", "цена - 3", "-3", "цена-2", "цена 2", "цена - 2", "-2"]
        for target in target_names:
            for col in df.columns:
                c_norm = str(col).lower().replace("–", "-").replace("—", "-").replace("−", "-").strip()
                if c_norm == target or c_norm.replace(" ", "") == target.replace(" ", ""):
                    found_col = col
                    break
            if found_col:
                break
                
        if not found_col:
            for col in df.columns:
                col_str = str(col).strip()
                if "-0.03" in col_str or "-3" in col_str or "-3%" in col_str or "-0.04" in col_str or "-4" in col_str or "-4%" in col_str:
                    found_col = col
                    break
                try:
                    f_val = float(col)
                    if abs(f_val + 0.03) < 0.001 or abs(f_val + 3.0) < 0.001 or abs(f_val + 0.04) < 0.001 or abs(f_val + 4.0) < 0.001:
                        found_col = col
                        break
                except (ValueError, TypeError):
                    pass

        if not found_col:
            raw_cols = list(df.columns)
            name_col = pick_column(raw_cols, DEFAULT_NAME_CANDIDATES)
            name_col_idx = raw_cols.index(name_col) if name_col in raw_cols else None
            min_valid = min(10, max(2, int(len(df) * 0.1)))
            valid_price_cols = []
            for idx, col in enumerate(raw_cols):
                if name_col_idx is not None and idx <= name_col_idx:
                    continue
                c_str = str(col).lower().replace("–", "-").replace("—", "-").replace("−", "-").strip()
                if any(x in c_str for x in ["заказ", "орг. уп", "орг.уп", "произ.", "производитель", "годности", "годность"]):
                    break
                valid_prices = 0
                for v in df.iloc[:, idx].dropna():
                    try:
                        if float(v) > 500:
                            valid_prices += 1
                    except (ValueError, TypeError):
                        pass
                if valid_prices >= min_valid:
                    valid_price_cols.append(col)
            if valid_price_cols:
                found_col = valid_price_cols[-1]
                    
        if found_col:
            return found_col
        if "Цена" in cols:
            return "Цена"
            
    return pick_price_column(cols, price_candidates)


def _excel_engine_for(path: Path) -> str:
    """Определяет движок чтения Excel по сигнатуре (magic bytes) файла."""
    try:
        with open(path, "rb") as fp:
            magic = fp.read(8)
        if magic.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return "xlrd"
        if magic.startswith(b"PK\x03\x04"):
            return "openpyxl"
    except Exception:
        pass
    return "openpyxl" if path.suffix.lower() == ".xlsx" else "xlrd"


def _grand_farm_header_row(
    path: Path,
    name_candidates: List[str],
    price_candidates: List[str],
) -> Optional[int]:
    """
    В прайсах «Гранд Фарм» заголовок основной таблицы ищется в пределах 1..10000 строк.
    """
    price_cands = {_normalize_col_for_match(p) for p in price_candidates}
    price_cands.update({"отпускная цена с ндс", "отпускная цена", "отпуск.цена с ндс", "отп. цена с ндс", "100%", "1", "1.0", "базовая цена"})
    name_cands = {_normalize_col_for_match(n) for n in name_candidates}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        for excel_row_1based, row in enumerate(
            ws.iter_rows(min_row=1, max_row=10000, values_only=True),
            start=1,
        ):
            normed: set = set()
            for v in row:
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                normed.add(_normalize_col_for_match(s))
            if normed & name_cands and normed & price_cands:
                return excel_row_1based - 1
    finally:
        wb.close()
    return None


def read_price_table(
    path: Path,
    key_candidates: List[str],
    name_candidates: List[str],
    price_candidates: List[str],
    stock_candidates: List[str],
    use_key: bool,
    use_name: bool,
    read_preset: Optional[str] = None,
) -> pd.DataFrame:
    """Читает прайс даже если заголовок не в первой строке."""
    engine = _excel_engine_for(path)
    read_path = path

    if "delpharm" in path.name.lower():
        df = pd.read_excel(path, header=None)
        if len(df) > 5:
            cols = []
            row3 = df.iloc[4]
            row4 = df.iloc[5]
            last_v3 = ""
            for c3, c4 in zip(row3, row4):
                v3 = str(c3).strip() if pd.notna(c3) and str(c3).strip() != "" else ""
                v4 = str(c4).strip() if pd.notna(c4) and str(c4).strip() != "" else ""
                if v3:
                    last_v3 = v3
                if v4:
                    if last_v3 and last_v3 != v4:
                        cols.append(f"{last_v3} {v4}")
                    else:
                        cols.append(v4)
                elif v3:
                    cols.append(v3)
                else:
                    cols.append("")
            df = df.iloc[6:]
            df.columns = cols
        df.columns = [_clean_col(c) for c in df.columns]
        return df

    use_promotion = read_preset == "drug_promotion" or (
        read_preset is None and any(x in path.name.lower() for x in ["drug promotion", "промоушен"])
    )
    if use_promotion:
        read_path = path
        try:
            with open(path, "rb"):
                pass
        except PermissionError:
            out_dir = path.parent / "output" / "_tmp_read"
            out_dir.mkdir(parents=True, exist_ok=True)
            read_path = out_dir / path.name
            shutil.copy2(path, read_path)
        except Exception:
            pass

        try:
            df_scan = pd.read_excel(read_path, engine=engine, header=None, nrows=400)
            hdr_idx = None
            for r_idx in range(len(df_scan)):
                row_vals = [str(val).lower().strip() for val in df_scan.iloc[r_idx] if pd.notna(val)]
                if "номенклатура" in row_vals and any("цена" in v for v in row_vals) and any("привязка" in v or "мини" in v for v in row_vals):
                    hdr_idx = r_idx
                    break
            if hdr_idx is not None:
                df = pd.read_excel(read_path, engine=engine, header=hdr_idx)
                df.columns = [_clean_col(c) for c in df.columns]
                return df
        except Exception:
            pass

    use_khoji = read_preset == "khoji_akbar" or (
        read_preset is None and ("Хожи Акбар" in path.stem or "khoji" in path.stem.lower())
    )
    use_grand = read_preset == "grand_farm" or (
        read_preset is None 
        and ("Гранд Фарм" in path.stem or "GRAND PHARM" in path.stem.upper() or "GRAND FARM" in path.stem.upper()) 
        and engine == "openpyxl"
    )

    if use_khoji:
        for try_hdr in [17, 11, 12, 13, 14, 15, 16, 18, 19, 20, 10, 9, 8, 7, 0, 1, 2, 3]:
            try:
                try:
                    df = pd.read_excel(path, engine=engine, header=try_hdr)
                except PermissionError:
                    out_dir = path.parent / "output" / "_tmp_read"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    read_path = out_dir / path.name
                    shutil.copy2(path, read_path)
                    df = pd.read_excel(read_path, engine=engine, header=try_hdr)
                df.columns = [_clean_col(c) for c in df.columns]
                cols_norm = [_normalize_col_for_match(c) for c in df.columns]
                has_n = any("товар" in c or "наименование" in c or "препарат" in c for c in cols_norm)
                has_p = any("цена" in c or "нарх" in c or "сумма" in c for c in cols_norm)
                if has_n and has_p:
                    return df
            except Exception:
                continue

    if use_grand:
        def _read_grand(headers: int) -> pd.DataFrame:
            return pd.read_excel(read_path, engine=engine, header=headers)

        hdr: Optional[int] = None
        try:
            hdr = _grand_farm_header_row(path, name_candidates, price_candidates)
        except Exception:
            hdr = None
        if hdr is None:
            hdr = 402
        try:
            df = _read_grand(hdr)
        except PermissionError:
            out_dir = path.parent / "output" / "_tmp_read"
            out_dir.mkdir(parents=True, exist_ok=True)
            read_path = out_dir / path.name
            shutil.copy2(path, read_path)
            df = _read_grand(hdr)
        df.columns = [_clean_col(c) for c in df.columns]
        grand_price_cands = list(price_candidates) + ["Отпускная цена с НДС", "Отпускная цена", "Отп. цена с НДС", "100%", "1", "1.0"]
        if pick_column(list(df.columns), name_candidates) and pick_price_column(
            list(df.columns), grand_price_cands
        ):
            return df
        try:
            hdr2 = _grand_farm_header_row(read_path, name_candidates, price_candidates)
        except Exception:
            hdr2 = None
        if hdr2 is not None and hdr2 != hdr:
            df = pd.read_excel(read_path, engine=engine, header=hdr2)
            df.columns = [_clean_col(c) for c in df.columns]
            if pick_column(list(df.columns), name_candidates) and pick_price_column(
                list(df.columns), grand_price_cands
            ):
                return df

    read_path = path
    try:
        with open(path, "rb"):
            pass
    except PermissionError:
        out_dir = path.parent / "output" / "_tmp_read"
        out_dir.mkdir(parents=True, exist_ok=True)
        read_path = out_dir / path.name
        shutil.copy2(path, read_path)
    except Exception:
        pass

    try:
        xl = pd.ExcelFile(read_path, engine=engine)
        sheets = xl.sheet_names
    except Exception as e:
        fallback_engine = "xlrd" if engine == "openpyxl" else "openpyxl"
        try:
            xl = pd.ExcelFile(read_path, engine=fallback_engine)
            sheets = xl.sheet_names
            engine = fallback_engine
        except Exception:
            sheets = [0]

    max_scan = 600
    price_cands = [_normalize_col_for_match(p) for p in price_candidates]
    name_cands = [_normalize_col_for_match(n) for n in name_candidates]

    # Ensure custom rules for this file/distributor are included in header candidates
    try:
        rules = load_distributor_rules()
        for r_k, r_v in rules.items():
            if r_k.lower() in str(read_path).lower() or r_k.lower() in str(read_path.name).lower():
                if r_v.get("p100_col"):
                    norm_c = _normalize_col_for_match(str(r_v["p100_col"]))
                    if norm_c and norm_c not in price_cands:
                        price_cands.append(norm_c)
                if r_v.get("p25_col"):
                    norm_c = _normalize_col_for_match(str(r_v["p25_col"]))
                    if norm_c and norm_c not in price_cands:
                        price_cands.append(norm_c)
                if r_v.get("name_col"):
                    norm_c = _normalize_col_for_match(str(r_v["name_col"]))
                    if norm_c and norm_c not in name_cands:
                        name_cands.append(norm_c)
    except Exception:
        pass

    price_cands_spaceless = {p.replace(" ", "") for p in price_cands if p}
    name_cands_spaceless = {n.replace(" ", "") for n in name_cands if n}

    errors = []
    for sheet in sheets:
        try:
            df0 = pd.read_excel(read_path, engine=engine, sheet_name=sheet, header=0)
            df0.columns = _make_columns_unique(df0.columns)
            cols0 = [_normalize_col_for_match(c) for c in df0.columns]
            cols0_spaceless = {c.replace(" ", "") for c in cols0 if c}
            if (any(p in cols0 for p in price_cands) or bool(cols0_spaceless & price_cands_spaceless)) and (any(n in cols0 for n in name_cands) or bool(cols0_spaceless & name_cands_spaceless)):
                return df0
        except Exception as e:
            errors.append(f"Sheet '{sheet}' fast path error: {e}")

        try:
            df_scan = pd.read_excel(read_path, engine=engine, sheet_name=sheet, header=None, nrows=max_scan)
            if not df_scan.empty:
                for r_idx in range(len(df_scan)):
                    row_series = df_scan.iloc[r_idx]
                    row_vals = [_normalize_col_for_match(str(val)) for val in row_series if pd.notna(val)]
                    row_spaceless = {v.replace(" ", "") for v in row_vals if v}
                    has_price = any(p in row_vals for p in price_cands) or bool(row_spaceless & price_cands_spaceless)
                    has_name = any(n in row_vals for n in name_cands) or bool(row_spaceless & name_cands_spaceless)
                    if has_price and has_name:
                        df = pd.read_excel(read_path, engine=engine, sheet_name=sheet, header=r_idx)
                        df.columns = _make_columns_unique(df.columns)
                        return df

                    if r_idx + 1 < len(df_scan):
                        next_row_series = df_scan.iloc[r_idx + 1]
                        combined_vals = []
                        for col_i in range(max(len(row_series), len(next_row_series))):
                            val1 = row_series[col_i] if col_i < len(row_series) else None
                            val2 = next_row_series[col_i] if col_i < len(next_row_series) else None
                            
                            parts = []
                            if pd.notna(val1):
                                parts.append(str(val1).strip())
                            if pd.notna(val2):
                                parts.append(str(val2).strip())
                            
                            if parts:
                                combined_vals.append(" ".join(parts))
                            else:
                                combined_vals.append("")
                        
                        norm_combined = [_normalize_col_for_match(c) for c in combined_vals]
                        has_price = any(p in norm_combined for p in price_cands)
                        has_name = any(n in norm_combined for n in name_cands)
                        
                        if has_price and has_name:
                            df = pd.read_excel(read_path, engine=engine, sheet_name=sheet, header=r_idx)
                            new_cols = []
                            for col_i in range(len(df.columns)):
                                col_name = df.columns[col_i]
                                next_row_val = next_row_series[col_i] if col_i < len(next_row_series) else None
                                
                                parts = []
                                if pd.notna(col_name) and not str(col_name).startswith("Unnamed:"):
                                    parts.append(str(col_name).strip())
                                if pd.notna(next_row_val):
                                    parts.append(str(next_row_val).strip())
                                
                                if parts:
                                    new_cols.append(" ".join(parts))
                                else:
                                    new_cols.append(f"Unnamed: {col_i}")
                                    
                            df.columns = _make_columns_unique(new_cols)
                            if not df.empty:
                                df = df.iloc[1:].reset_index(drop=True)
                            return df
        except Exception as e:
            errors.append(f"Sheet '{sheet}' scan path error: {e}")

    raise ValueError(f"Не удалось найти строку заголовков с ценой и наименованием в файле: {path}. Ошибки по листам: {errors}")
