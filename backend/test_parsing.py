import openpyxl
import pandas as pd
from pathlib import Path
from app.core.pipeline import find_distributor_columns, pick_price_columns, _display_label
from app.core.excel_reader import read_price_table, pick_column, pick_price_column
from app.defaults import DEFAULT_COLUMNS, DEFAULT_PRODUCERS

upload_dir = Path("/app/data/uploads/1")
key_c = DEFAULT_COLUMNS["key_candidates"]
name_c = DEFAULT_COLUMNS["name_candidates"]
price_c = DEFAULT_COLUMNS["price_candidates"]
stock_c = DEFAULT_COLUMNS["stock_candidates"]
prod_c = DEFAULT_COLUMNS["producer_candidates"]

for p in sorted(upload_dir.glob("*")):
    if p.is_dir() or not (p.suffix in ['.xlsx', '.xls']):
        continue
    lbl = _display_label("", p.name)
    col_mapping = find_distributor_columns(lbl)
    print(f"\n--- File: {p.name} (label: '{lbl}') ---")
    print(f"Distributor columns mapping in template: {col_mapping}")
    try:
        df = read_price_table(p, key_c, name_c, price_c, stock_c, use_key=True, use_name=True)
        cols = list(df.columns)
        print("Sheet Columns:", cols)
        
        name_col = pick_column(cols, name_c)
        producer_col = pick_column(cols, prod_c)
        p25_col, p100_col = pick_price_columns(cols, price_c)
        
        # Check special distributor logic in pipeline:
        if "meros" in p.name.lower() or "мерос" in p.name.lower():
            for col in df.columns:
                c_low = str(col).lower().strip()
                if c_low in ["цена договорная", "ценадоговорная", "цена"]:
                    p25_col = col
                    break
            if not p25_col and "Цена" in df.columns:
                p25_col = "Цена"
            for col in df.columns:
                c_low = str(col).lower().strip()
                if c_low in ["цена 100%", "цена100%", "100% оплата", "100%оплата", "при 100% оплате", "при100%оплате"]:
                    p100_col = col
                    break
            if not p100_col and "Цена 100%" in df.columns:
                p100_col = "Цена 100%"
        elif "grand" in p.name.lower() or "гранд" in p.name.lower() or "promotion" in p.name.lower() or "промоушен" in p.name.lower():
            is_100 = False
            is_25 = False
            fn_low = p.name.lower()
            if "100" in fn_low:
                is_100 = True
            elif "25" in fn_low:
                is_25 = True
            price_cols_list = []
            for col in df.columns:
                col_clean = " ".join(str(col).lower().split())
                if "без ндс" in col_clean or "безндс" in col_clean:
                    continue
                if col_clean in ["ндс", "ндс%", "ставка ндс", "ставка ндс, %", "ндс, %", "заказ", "заказы", "кол-во", "кол во", "сумма", "sum", "total", "количество"]:
                    continue
                if any(x in col_clean for x in ["сумма", "sum", "total"]):
                    continue
                price_cols_list.append((col, col_clean))
            col_100_found = None
            col_25_found = None
            for col, col_clean in price_cols_list:
                col_clean_no_dosage = col_clean.replace("мл", "").replace("мг", "").replace("таб", "").replace("кап", "")
                if "100" in col_clean_no_dosage:
                    col_100_found = col
                    is_100 = True
                elif "25" in col_clean_no_dosage:
                    col_25_found = col
                    is_25 = True
            p25_col = None
            p100_col = None
            if col_100_found and col_25_found:
                p100_col = col_100_found
                p25_col = col_25_found
            elif is_100:
                p100_col = col_100_found
                if not p100_col:
                    valid_cols = [c for c, _ in price_cols_list]
                    p100_col = pick_price_column(valid_cols, price_c)
            else:
                p25_col = col_25_found
                if not p25_col:
                    for col, col_clean in price_cols_list:
                        if any(x in col_clean for x in ["отпускная цена с ндс", "отпуск.цена с ндс", "отпускная цена", "отпуск.цена", "отп. цена", "отп.цена"]):
                            p25_col = col
                            break
                if not p25_col:
                    valid_cols = [c for c, _ in price_cols_list]
                    p25_col = pick_price_column(valid_cols, price_c)
        elif "luxe" in p.name.lower() or "люкс" in p.name.lower():
            p100_col = None
            p25_col = None
            col_price = pick_price_column(list(df.columns), price_c)
            if "100" in p.name.lower():
                p100_col = col_price
            elif "завод" in p.name.lower() or "zavod" in p.name.lower() or "25" in p.name.lower():
                p25_col = col_price
            else:
                p25_col, p100_col = pick_price_columns(list(df.columns), price_c)
        elif "biotek" in p.name.lower() or "биотек" in p.name.lower():
            raw_cols = list(df.columns)
            name_col_idx = raw_cols.index(name_col) if name_col in raw_cols else None
            min_valid = min(10, max(2, int(len(df) * 0.1)))
            price_col_indices = []
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
                    price_col_indices.append(idx)
            if price_col_indices:
                p25_col = raw_cols[price_col_indices[0]]
                p100_col = raw_cols[price_col_indices[-1]]
            else:
                p25_col = pick_price_column(raw_cols, price_c)
                p100_col = p25_col
        print(f"RESULT -> name_col: '{name_col}', p25_col: '{p25_col}', p100_col: '{p100_col}'")
    except Exception as ex:
        print("ERROR processing file:", ex)
