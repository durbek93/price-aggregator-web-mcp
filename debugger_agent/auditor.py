# -*- coding: utf-8 -*-
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import openpyxl
import pandas as pd

logger = logging.getLogger("debugger_agent.auditor")

MATERIA_SYNONYMS = {
    "эргоферон": ["эргоферон", "ergoferon"],
    "анаферон детский": ["анаферон дет", "анаферон для дет", "anaferon child"],
    "анаферон детский капли": ["анаферон дет кап", "анаферон капл", "анаферон 25мл"],
    "анаферон": ["анаферон таб", "анаферон взр", "anaferon"],
    "ренгалин таб": ["ренгалин таб", "ренгалин табл", "rengalin tab"],
    "ренгалин раствор": ["ренгалин р-р", "ренгалин раст", "ренгалин 100", "rengalin sol"],
    "тенотен": ["тенотен таб", "тенотен взр", "tenoten"],
    "тенотен детский": ["тенотен дет", "tenoten child"],
    "диваза": ["диваза", "divaza"],
    "колофорт": ["колофорт", "kolofort", "colofort"],
    "афалаза": ["афалаза", "afalaza"],
    "афала": ["афала таб", "афала №100", "afala"],
    "импаза": ["импаза", "impaza"],
    "климаксан гр": ["климаксан гр", "климаксан гранул"],
    "климаксан таб": ["климаксан таб", "klimaksan"],
    "млекоин": ["млекоин", "mlekoin"],
    "успокой": ["успокой", "uspokoy"],
    "фарингомед": ["фарингомед", "faringomed"],
    "бризантин": ["бризантин", "brizantin"],
    "проспекта": ["проспекта", "prospekta"],
    "кардос": ["кардос", "kardos"],
}

MATERIA_KEY_TO_TEMPLATE_PRODUCT = {
    "эргоферон": "Эргоферон №20",
    "анаферон детский": "Анаферон детский №20",
    "анаферон детский капли": "Анаферон детский №20 капли",
    "анаферон": "Анаферон №20",
    "ренгалин таб": "Ренгалин таб №20",
    "ренгалин раствор": "Ренгалин раствор 100 мл",
    "тенотен": "Тенотен №20",
    "тенотен детский": "Тенотен детский №20",
    "тенотен 40": "Тенотен №40",
    "тенотен детский 40": "Тенотен детский №40",
    "диваза": "Диваза №100",
    "колофорт": "Колофорт №100",
    "афалаза": "Афалаза таб № 100",
    "афала": "Афала №100",
    "импаза": "Импаза №20",
    "климаксан гр": "Климаксан гр  10 гр",
    "климаксан таб": "Климаксан таб №20",
    "млекоин": "Млекоин гр 10 гр",
    "успокой": "Успокой №20",
    "фарингомед": "Фарингомед №20",
}

DISTRIBUTOR_MAP = {
    "zenta": {"label": "ЗЕНТА ФАРМ", "col_25": 3, "col_100": 4, "patterns": ["zenta", "зента"]},
    "grand": {"label": "ГРАНД ФАРМ", "col_25": 5, "col_100": 6, "patterns": ["grand", "гранд"]},
    "meros": {"label": "MEROS PHARM", "col_25": 7, "col_100": 8, "patterns": ["meros", "мерос"]},
    "promotion": {"label": "ДРАГ ПРОМОУШЕН", "col_25": 9, "col_100": 10, "patterns": ["promotion", "промоушен"]},
    "choice": {"label": "PHARMA CHOICE", "col_25": 11, "col_100": None, "patterns": ["choice", "чойс"]},
    "biotek": {"label": "БИОТЕК ФАРМ", "col_25": 12, "col_100": 13, "patterns": ["biotek", "биотек"]},
    "luxe": {"label": "ФАРМ ЛЮКС", "col_25": 14, "col_100": 15, "patterns": ["luxe", "люкс"]},
    "aero": {"label": "AERO PHARM", "col_25": 16, "col_100": 17, "patterns": ["aero", "аэро"]},
    "delpharm": {"label": "DELPHARM", "col_25": 18, "col_100": None, "patterns": ["delpharm", "дельфарм"]},
}


@dataclass
class Discrepancy:
    distributor_key: str
    distributor_label: str
    raw_filename: str
    raw_filepath: Path
    issue_type: str  # 'missing_100_percent', 'missing_25_percent', 'product_missing', 'price_mismatch'
    description: str
    affected_products: List[str] = field(default_factory=list)
    raw_sample_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    svodny_filepath: Path
    is_valid: bool
    discrepancies: List[Discrepancy] = field(default_factory=list)
    summary_text: str = ""
    checked_distributors: List[str] = field(default_factory=list)


def _read_excel_file(path: Path) -> pd.DataFrame:
    """Reads Excel file handling both xls and xlsx with header auto-detection."""
    suffix = path.suffix.lower()
    engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
    try:
        # First read without header to inspect rows
        df_raw = pd.read_excel(path, sheet_name=0, header=None, engine=engine)
        
        # Find header row
        hdr_idx = 0
        for r_i in range(min(500, len(df_raw))):
            row_vals = [str(x).lower().strip() for x in df_raw.iloc[r_i] if pd.notna(x)]
            if any(k in row_vals for k in ["наименование", "название", "товар", "номенклатура", "препарат", "медикамент"]):
                hdr_idx = r_i
                break
                
        df = pd.read_excel(path, sheet_name=0, header=hdr_idx, engine=engine)
        # Deduplicate column names
        seen = {}
        new_cols = []
        for c in df.columns:
            c_str = str(c).strip() if pd.notna(c) else "Unnamed"
            if not c_str:
                c_str = "Unnamed"
            if c_str in seen:
                seen[c_str] += 1
                new_cols.append(f"{c_str}_{seen[c_str]}")
            else:
                seen[c_str] = 0
                new_cols.append(c_str)
        df.columns = new_cols
        return df
    except Exception as e:
        logger.error(f"Error reading raw excel file {path}: {e}")
        return pd.DataFrame()


def find_latest_svodny(output_dir: Path) -> Optional[Path]:
    """Finds the most recently modified consolidated price file."""
    candidates = []
    # Search in output_dir and all subdirectories (like output_dir/1)
    for p in output_dir.glob("**/Сводный*.xlsx"):
        if p.is_file() and not p.name.startswith("~$"):
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return candidates[0]


def audit_svodny_price(svodny_path: Path, upload_dir: Path) -> AuditReport:
    """
    Performs full cross-check of Materia Medica products in the consolidated price list
    against raw supplier price files in upload_dir.
    """
    if not svodny_path.exists():
        return AuditReport(
            svodny_filepath=svodny_path,
            is_valid=False,
            summary_text=f"Файл сводного прайса не найден: {svodny_path}"
        )

    wb = openpyxl.load_workbook(svodny_path, data_only=True)
    sheet_name = "СвПрайс" if "СвПрайс" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]

    # Read template products from rows 7 to 24
    template_products: List[Tuple[int, str]] = []
    for r in range(7, 25):
        val = ws.cell(row=r, column=2).value
        if val:
            template_products.append((r, str(val).strip()))

    discrepancies: List[Discrepancy] = []
    checked_distributors: List[str] = []

    # Get list of all raw files in upload_dir
    raw_files = [p for p in upload_dir.glob("**/*.*") if p.suffix.lower() in [".xlsx", ".xls"] and not p.name.startswith("~$") and "history" not in str(p)]

    for dist_key, dist_info in DISTRIBUTOR_MAP.items():
        dist_label = dist_info["label"]
        col_25 = dist_info["col_25"]
        col_100 = dist_info["col_100"]
        patterns = dist_info["patterns"]

        # Find matching raw files for this distributor
        matched_raw_files = []
        for rf in raw_files:
            fn_low = rf.name.lower()
            if any(p in fn_low for p in patterns):
                matched_raw_files.append(rf)

        if not matched_raw_files:
            continue

        checked_distributors.append(dist_label)

        # Read prices already written in the consolidated sheet for this distributor
        sheet_prices_25 = {}
        sheet_prices_100 = {}
        for r_idx, p_name in template_products:
            val_25 = ws.cell(row=r_idx, column=col_25).value if col_25 else None
            val_100 = ws.cell(row=r_idx, column=col_100).value if col_100 else None
            sheet_prices_25[p_name] = val_25
            if col_100:
                sheet_prices_100[p_name] = val_100

        # Scan each raw file of this distributor
        for raw_path in matched_raw_files:
            df_raw = _read_excel_file(raw_path)
            if df_raw.empty:
                continue

            # Find name column
            name_col = None
            for c in df_raw.columns:
                c_low = str(c).lower()
                if any(k in c_low for k in ["наименование", "название", "товар", "номенклатура", "препарат", "медикамент"]):
                    name_col = c
                    break
            if not name_col:
                continue

            # Find Materia Medica rows in the raw file
            materia_rows = []
            for r_i in range(len(df_raw)):
                n_val = str(df_raw.iloc[r_i].get(name_col, "")).lower()
                for key_term in MATERIA_SYNONYMS:
                    if key_term in n_val:
                        materia_rows.append((df_raw.iloc[r_i], key_term))
                        break

            if not materia_rows:
                continue

            # Check available numeric price columns in raw file
            numeric_cols = []
            for c in df_raw.columns:
                if c == name_col:
                    continue
                c_low = str(c).lower()
                if any(x in c_low for x in ["орг. уп", "произ.", "производитель", "годности", "годность", "код", "арт"]):
                    continue
                valid_cnt = 0
                for v in df_raw[c].dropna().head(100):
                    try:
                        if float(v) > 500:
                            valid_cnt += 1
                    except (ValueError, TypeError):
                        pass
                if valid_cnt >= 5:
                    numeric_cols.append(c)

            # Check 1: Missing 100% price column
            if col_100 is not None:
                all_100_none = all(sheet_prices_100.get(p) is None for _, p in template_products)
                has_discount_columns = len(numeric_cols) > 1 or any(x in raw_path.name.lower() for x in ["100", "скид"])
                
                # If raw file has discount columns but 100% in sheet is completely empty
                if all_100_none and has_discount_columns:
                    affected = [p for _, p in template_products if sheet_prices_25.get(p) is not None]
                    discrepancies.append(Discrepancy(
                        distributor_key=dist_key,
                        distributor_label=dist_label,
                        raw_filename=raw_path.name,
                        raw_filepath=raw_path,
                        issue_type="missing_100_percent",
                        description=f"Дистрибьютор {dist_label}: колонка цены 100% (колонка {col_100}) полностью пуста, хотя в файле {raw_path.name} обнаружено несколько колонок цен {numeric_cols}.",
                        affected_products=affected,
                        raw_sample_data={
                            "columns": list(df_raw.columns),
                            "numeric_price_cols": numeric_cols,
                            "sample_row": materia_rows[0][0].to_dict() if materia_rows else {}
                        }
                    ))

            # Check 2: Entirely missing distributor
            all_25_none = all(sheet_prices_25.get(p) is None for _, p in template_products)
            all_100_none = all(sheet_prices_100.get(p) is None for _, p in template_products) if col_100 else True
            if all_25_none and all_100_none and len(materia_rows) >= 2:
                discrepancies.append(Discrepancy(
                    distributor_key=dist_key,
                    distributor_label=dist_label,
                    raw_filename=raw_path.name,
                    raw_filepath=raw_path,
                    issue_type="distributor_completely_missing",
                    description=f"Дистрибьютор {dist_label}: в файле {raw_path.name} найдено {len(materia_rows)} позиций Материя Медика, но в сводном прайсе все ячейки пустые.",
                    affected_products=[p for _, p in template_products],
                    raw_sample_data={
                        "columns": list(df_raw.columns),
                        "numeric_price_cols": numeric_cols,
                        "sample_row": materia_rows[0][0].to_dict() if materia_rows else {}
                    }
                ))

            # Check 3: Missing specific Materia Medica products found in raw file
            elif not (all_25_none and all_100_none):
                seen_missing_target = set()
                for m_row, key_term in materia_rows:
                    target_prod = MATERIA_KEY_TO_TEMPLATE_PRODUCT.get(key_term)
                    if not target_prod or target_prod in seen_missing_target:
                        continue
                    
                    # Check if price exists in this raw row
                    has_price = False
                    for c in numeric_cols:
                        v = m_row.get(c)
                        try:
                            if pd.notna(v) and float(v) > 500:
                                has_price = True
                                break
                        except (ValueError, TypeError):
                            pass
                    if not has_price:
                        continue

                    raw_product_name = str(m_row.get(name_col, "")).strip()
                    val_25 = sheet_prices_25.get(target_prod)
                    val_100 = sheet_prices_100.get(target_prod) if col_100 else None

                    is_100_file = "100" in raw_path.name.lower()
                    is_25_file = "25" in raw_path.name.lower()

                    if is_100_file:
                        if col_100 and val_100 is None:
                            seen_missing_target.add(target_prod)
                            discrepancies.append(Discrepancy(
                                distributor_key=dist_key,
                                distributor_label=dist_label,
                                raw_filename=raw_path.name,
                                raw_filepath=raw_path,
                                issue_type="product_missing",
                                description=f"Дистрибьютор {dist_label}: в файле {raw_path.name} найден препарат «{raw_product_name}», но колонка 100% для «{target_prod}» в сводном прайсе пустая.",
                                affected_products=[target_prod],
                                raw_sample_data={
                                    "columns": list(df_raw.columns),
                                    "numeric_price_cols": numeric_cols,
                                    "raw_product_name": raw_product_name,
                                    "target_template_product": target_prod,
                                    "sample_row": m_row.to_dict()
                                }
                            ))
                    elif is_25_file:
                        if col_25 and val_25 is None:
                            seen_missing_target.add(target_prod)
                            discrepancies.append(Discrepancy(
                                distributor_key=dist_key,
                                distributor_label=dist_label,
                                raw_filename=raw_path.name,
                                raw_filepath=raw_path,
                                issue_type="product_missing",
                                description=f"Дистрибьютор {dist_label}: в файле {raw_path.name} найден препарат «{raw_product_name}», но колонка 25% для «{target_prod}» в сводном прайсе пустая.",
                                affected_products=[target_prod],
                                raw_sample_data={
                                    "columns": list(df_raw.columns),
                                    "numeric_price_cols": numeric_cols,
                                    "raw_product_name": raw_product_name,
                                    "target_template_product": target_prod,
                                    "sample_row": m_row.to_dict()
                                }
                            ))
                    else:
                        if val_25 is None and (col_100 is None or val_100 is None):
                            seen_missing_target.add(target_prod)
                            discrepancies.append(Discrepancy(
                                distributor_key=dist_key,
                                distributor_label=dist_label,
                                raw_filename=raw_path.name,
                                raw_filepath=raw_path,
                                issue_type="product_missing",
                                description=f"Дистрибьютор {dist_label}: в файле {raw_path.name} найден препарат «{raw_product_name}», но ячейка «{target_prod}» в сводном прайсе пустая.",
                                affected_products=[target_prod],
                                raw_sample_data={
                                    "columns": list(df_raw.columns),
                                    "numeric_price_cols": numeric_cols,
                                    "raw_product_name": raw_product_name,
                                    "target_template_product": target_prod,
                                    "sample_row": m_row.to_dict()
                                }
                            ))

    is_valid = (len(discrepancies) == 0)
    if is_valid:
        summary = f"✅ Аудит пройден успешно. Проверено {len(checked_distributors)} дистрибьюторов ({', '.join(checked_distributors)}). Ошибок и пропусков по препаратам Материя Медика не обнаружено."
    else:
        summary = f"⚠️ Обнаружено {len(discrepancies)} расхождений при аудите сводного прайса {svodny_path.name}."

    return AuditReport(
        svodny_filepath=svodny_path,
        is_valid=is_valid,
        discrepancies=discrepancies,
        summary_text=summary,
        checked_distributors=checked_distributors
    )
