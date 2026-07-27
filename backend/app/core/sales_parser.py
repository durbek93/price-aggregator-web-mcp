# -*- coding: utf-8 -*-
import os
import re
import logging
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict
import pandas as pd

logger = logging.getLogger(__name__)

def clean_num(val: Any) -> int:
    """Безопасно очищает и конвертирует значение в целое число (игнорируя сбои)."""
    if pd.isna(val) or val is None:
        return 0
    val_str = str(val).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not val_str or val_str.lower() in ["nan", "none", "-"]:
        return 0
    try:
        return int(float(val_str))
    except (ValueError, TypeError):
        return 0

def parse_sales_excel_fast(file_path: Path, target_city: str = "Фергана") -> Optional[Dict[str, Any]]:
    """
    Высокоскоростной парсер Excel файлов продаж с прямым чтением XML структуры (zipfile).
    Считывает итоговые колонки 'ВСЕГО: РЕАЛИЗАЦИЯ' и 'ВСЕГО: ОСТАТКИ',
    а также разбивку по дистрибьюторам для целевого города (Фергана).
    """
    if not file_path.exists():
        logger.error(f"Sales file does not exist: {file_path}")
        return None

    try:
        with zipfile.ZipFile(file_path, 'r') as z:
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
                for elem in tree.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
                    shared_strings.append(elem.text or '')

            sheet_xml = z.read('xl/worksheets/sheet1.xml')
            tree = ET.fromstring(sheet_xml)
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

            def get_val(c):
                t = c.attrib.get('t')
                v = c.find('s:v', ns)
                if v is None: return ''
                val = v.text
                if t == 's' and val is not None and int(val) < len(shared_strings):
                    return shared_strings[int(val)]
                return val or ''

            rows = []
            for r in tree.findall('.//s:row', ns):
                r_num = int(r.attrib.get('r'))
                row_dict = {}
                for c in r.findall('s:c', ns):
                    cell_ref = c.attrib.get('r')
                    val = get_val(c)
                    row_dict[cell_ref] = val
                rows.append((r_num, row_dict))
    except Exception as e:
        logger.error(f"Error reading zip XML Excel {file_path}: {e}")
        return None

    # Дистрибьюторы шапка (Row 6)
    dist_row = rows[5][1] if len(rows) > 5 else {}
    sub_row = rows[6][1] if len(rows) > 6 else {}

    col_dist_map = {}
    current_dist = None

    for cell_ref, val in dist_row.items():
        col_let = "".join([c for c in cell_ref if c.isalpha()])
        v_s = str(val).strip()
        if v_s and v_s.lower() not in ['товар', 'регионы', 'nan', 'none', 'всего:', 'всего', 'итого']:
            current_dist = re.sub(r'^(ООО|ЧП|ИП|СП)\s*"?|"?$', '', v_s, flags=re.IGNORECASE).strip()
        elif v_s.lower() in ['всего:', 'всего', 'итого']:
            current_dist = None

        sub_val = str(sub_row.get(f'{col_let}7', '')).strip().lower()
        if current_dist:
            if 'реализаци' in sub_val:
                col_dist_map[col_let] = (current_dist, 'realization')
            elif 'остаток' in sub_val and 'поступлени' not in sub_val:
                col_dist_map[col_let] = (current_dist, 'stock')

    total_real_col = "AY"
    total_stock_col = "AZ"

    current_product = ""
    records = []
    total_realization = 0
    total_stock = 0
    period_label = file_path.stem.capitalize()

    dist_totals = defaultdict(lambda: {"realization": 0, "stock": 0})

    for r_num, r_data in rows[5:]:
        val_a = r_data.get(f'A{r_num}', '').strip()
        if val_a and val_a.lower() not in ['итоги', 'итого', 'nan', 'none', 'товар', 'регионы']:
            current_product = val_a

        val_b = r_data.get(f'B{r_num}', '').strip()
        if current_product and target_city.lower() in val_b.lower():
            ay_val = r_data.get(f'{total_real_col}{r_num}', '0')
            az_val = r_data.get(f'{total_stock_col}{r_num}', '0')
            
            try: real_num = abs(int(float(str(ay_val).replace(' ', '').replace('\xa0', ''))))
            except: real_num = 0
            
            try: stock_num = abs(int(float(str(az_val).replace(' ', '').replace('\xa0', ''))))
            except: stock_num = 0

            total_realization += real_num
            total_stock += stock_num

            # Считаем дистрибьюторов по колонкам
            for col_let, (d_name, m_type) in col_dist_map.items():
                cell_val = r_data.get(f'{col_let}{r_num}', '0')
                try: c_num = abs(int(float(str(cell_val).replace(' ', '').replace('\xa0', ''))))
                except: c_num = 0
                if m_type == 'realization':
                    dist_totals[d_name]["realization"] += c_num
                elif m_type == 'stock':
                    dist_totals[d_name]["stock"] += c_num

            records.append({
                "product": current_product,
                "distributor": "ВСЕГО",
                "realization_units": real_num,
                "stock_units": stock_num,
                "period": period_label,
                "city": f"г. {target_city}"
            })

    return {
        "file_name": file_path.name,
        "period": period_label,
        "city": f"г. {target_city}",
        "total_realization": total_realization,
        "total_stock": total_stock,
        "dist_totals": dict(dist_totals),
        "records": records
    }


def parse_single_sales_file(file_path: Path, target_city: str = "Фергана") -> Optional[Dict[str, Any]]:
    """Парсит один Excel-файл продаж."""
    return parse_sales_excel_fast(file_path, target_city=target_city)


def aggregate_sales_data(sales_dir: Path, target_city: str = "г. Фергана") -> Dict[str, Any]:
    """
    Агрегирует все файлы продаж из директории `sales_dir` за весь период.
    Возвращает полную помесячную и попрепаратную структуру данных для ИИ-Аналитика.
    """
    if not sales_dir.exists():
        return {
            "meta": {"total_files": 0, "city": target_city, "periods": []},
            "summary": {"total_realization": 0, "total_stock": 0},
            "by_month": {},
            "by_distributor": {},
            "by_product": {},
            "monthly_trend": []
        }

    month_order = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]

    def get_month_idx(p: Path):
        fname = p.name.lower()
        for idx, m in enumerate(month_order):
            if m in fname:
                return idx
        return 99

    excel_files = sorted(
        [p for p in sales_dir.iterdir() if p.is_file() and p.suffix.lower() in [".xlsx", ".xls"]],
        key=get_month_idx
    )

    all_records = []
    periods_found = []
    total_real_all = 0
    total_stock_all = 0
    monthly_trend = []
    by_month = {}

    global_dist_totals = defaultdict(lambda: {"realization": 0, "stock": 0})

    for fpath in excel_files:
        parsed = parse_sales_excel_fast(fpath, target_city="Фергана")
        if parsed and parsed.get("records"):
            period = parsed["period"]
            periods_found.append(period)
            all_records.extend(parsed["records"])
            total_real_all += parsed["total_realization"]
            total_stock_all += parsed["total_stock"]

            month_prod_map = {}
            for rec in parsed["records"]:
                month_prod_map[rec["product"]] = {
                    "realization_units": rec["realization_units"],
                    "stock_units": rec["stock_units"]
                }

            by_month[period] = {
                "total_realization": parsed["total_realization"],
                "total_stock": parsed["total_stock"],
                "products": month_prod_map
            }

            monthly_trend.append({
                "period": period,
                "realization_units": parsed["total_realization"],
                "stock_units": parsed["total_stock"]
            })

            for d_name, d_vals in parsed.get("dist_totals", {}).items():
                global_dist_totals[d_name]["realization"] += d_vals["realization"]
                global_dist_totals[d_name]["stock"] += d_vals["stock"]

    if not all_records:
        return {
            "meta": {"total_files": len(excel_files), "city": target_city, "periods": periods_found},
            "summary": {"total_realization": 0, "total_stock": 0},
            "by_month": {},
            "by_distributor": {},
            "by_product": {},
            "monthly_trend": []
        }

    product_totals = {}
    for r in all_records:
        prod = r["product"]
        real = r["realization_units"]
        stk = r["stock_units"]
        period = r["period"]

        if prod not in product_totals:
            product_totals[prod] = {
                "realization_total": 0,
                "latest_stock": 0,
                "monthly_realization": {},
                "monthly_stock": {}
            }
        product_totals[prod]["realization_total"] += real
        product_totals[prod]["latest_stock"] = stk
        product_totals[prod]["monthly_realization"][period] = real
        product_totals[prod]["monthly_stock"][period] = stk

    by_product = {}
    for prod, vals in sorted(product_totals.items(), key=lambda x: x[1]["realization_total"], reverse=True):
        by_product[prod] = {
            "realization_units_total_2025": vals["realization_total"],
            "latest_stock_units": vals["latest_stock"],
            "share_percent": round((vals["realization_total"] / total_real_all) * 100, 2) if total_real_all > 0 else 0,
            "monthly_realization": vals["monthly_realization"],
            "monthly_stock": vals["monthly_stock"]
        }

    by_distributor = {}
    sum_dist_real = sum(d["realization"] for d in global_dist_totals.values()) or 1
    for d_name, d_vals in sorted(global_dist_totals.items(), key=lambda x: x[1]["realization"], reverse=True):
        if d_vals["realization"] > 0 or d_vals["stock"] > 0:
            by_distributor[d_name] = {
                "realization_units": d_vals["realization"],
                "stock_units": d_vals["stock"],
                "share_percent": round((d_vals["realization"] / sum_dist_real) * 100, 2)
            }

    return {
        "meta": {
            "city": target_city,
            "total_files": len(excel_files),
            "periods": periods_found
        },
        "summary": {
            "total_units": total_real_all,
            "total_realization": total_real_all,
            "total_stock_latest": monthly_trend[-1]["stock_units"] if monthly_trend else 0
        },
        "monthly_trend": monthly_trend,
        "by_month": by_month,
        "by_distributor": by_distributor,
        "by_product": by_product
    }
