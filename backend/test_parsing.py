import openpyxl
import pandas as pd
from pathlib import Path
from app.core.pipeline import find_distributor_columns, pick_price_columns, _display_label, load_distributor_rules, _find_matching_col
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
        
        fn_low = p.name.lower()
        lbl_low = lbl.lower()
        
        dist_rules = load_distributor_rules()
        rule = None
        is_multi_file_dist = any(d in lbl_low or d in fn_low for d in ["grand", "гранд", "promotion", "промоушен", "промоушн", "luxe", "люкс"])
        
        if not is_multi_file_dist:
            for r_key, r_val in dist_rules.items():
                if r_key.lower() in lbl_low or r_key.lower() in fn_low:
                    rule = r_val
                    break
        
        if rule:
            matched_name = _find_matching_col(rule.get("name_col"), list(df.columns))
            if matched_name:
                name_col = matched_name
            matched_p25 = _find_matching_col(rule.get("p25_col"), list(df.columns))
            if matched_p25:
                p25_col = matched_p25
            matched_p100 = _find_matching_col(rule.get("p100_col"), list(df.columns))
            if matched_p100:
                p100_col = matched_p100
        elif "meros" in fn_low or "мерос" in fn_low or "meros" in lbl_low or "мерос" in lbl_low:
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
        elif any(d in fn_low or d in lbl_low for d in ["grand", "гранд", "promotion", "промоушен", "промоушн"]):
            is_100 = "100" in fn_low
            is_25 = "25" in fn_low or not is_100
            
            col_price = None
            patterns = [
                ["отпускная цена с ндс", "отпуск.цена с ндс", "отп. цена с ндс"],
                ["цена с ндс", "цена (с ндс)", "цена с ндс 100%", "цена с ндс 25%"],
                ["отпускная цена", "отпуск.цена", "отп. цена", "отп.цена"],
                ["цена", "price", "нарх"],
                ["базовая цена"]
            ]
            for pattern_group in patterns:
                for col in df.columns:
                    col_clean = " ".join(str(col).lower().split())
                    if "без ндс" in col_clean or "безндс" in col_clean:
                        continue
                    if col_clean in ["ндс", "ндс%", "ставка ндс", "ставка ндс, %", "ндс, %", "заказ", "заказы", "кол-во", "кол во", "сумма", "sum", "total", "количество"]:
                        continue
                    if any(x in col_clean for x in ["сумма", "sum", "total"]):
                        continue
                    if any(p == col_clean or p in col_clean for p in pattern_group):
                        col_price = col
                        break
                if col_price:
                    break
                    
            if not col_price:
                valid_cols = [c for c in df.columns if "без ндс" not in str(c).lower() and "безндс" not in str(c).lower()]
                col_price = pick_price_column(valid_cols, price_c)
                
            if is_100:
                p100_col = col_price
                p25_col = None
            else:
                p25_col = col_price
                p100_col = None
        elif "luxe" in fn_low or "люкс" in fn_low or "luxe" in lbl_low or "люкс" in lbl_low:
            col_price = None
            patterns = [
                ["цена с ндс", "цена (с ндс)", "цена с ндс 100%", "цена с ндс 25%"],
                ["отпускная цена с ндс", "отпуск.цена с ндс", "отп. цена с ндс"],
                ["отпускная цена", "отпуск.цена", "отп. цена", "отп.цена"],
                ["цена", "price", "нарх"],
                ["базовая цена"]
            ]
            for pattern_group in patterns:
                for col in df.columns:
                    col_clean = " ".join(str(col).lower().split())
                    if "без ндс" in col_clean or "безндс" in col_clean:
                        continue
                    if col_clean in ["ндс", "ндс%", "ставка ндс", "ставка ндс, %", "ндс, %", "заказ", "заказы", "кол-во", "кол во", "сумма", "sum", "total", "количество"]:
                        continue
                    if any(x in col_clean for x in ["сумма", "sum", "total"]):
                        continue
                    if any(p == col_clean or p in col_clean for p in pattern_group):
                        col_price = col
                        break
                if col_price:
                    break
                    
            if not col_price:
                col_price = pick_price_column(list(df.columns), price_c)
                
            if "100" in fn_low:
                p100_col = col_price
                p25_col = None
            else:
                p25_col = col_price
                p100_col = None
        elif "biotek" in fn_low or "биотек" in fn_low or "biotek" in lbl_low or "биотек" in lbl_low or "biotech" in fn_low or "спец" in fn_low or "спец" in lbl_low:
            raw_cols = list(df.columns)
            name_col_idx = raw_cols.index(name_col) if name_col in raw_cols else None

            explicit_100_col = None
            explicit_25_col = None
            for col in raw_cols:
                c_clean = str(col).strip().lower().replace("–", "-").replace("—", "-").replace("−", "-")
                if any(c_clean == t or c_clean.replace(" ", "") == t.replace(" ", "") or t in c_clean for t in [
                    "цена-4", "цена 4", "цена - 4", "-4", "-4%", 
                    "цена-3", "цена 3", "цена - 3", "-3", "-3%", 
                    "цена-2", "цена 2", "цена - 2", "-2", "-2%", 
                    "100%", "цена 100%", "спец прайс", "спец. прайс", "спецпрайс",
                    "спец цена", "спец. цена", "спеццена", "цена спец", "цена со скидкой"
                ]):
                    explicit_100_col = col
                if any(c_clean == t or c_clean.replace(" ", "") == t.replace(" ", "") for t in ["цена", "базовая цена", "отпускная цена", "отп.цена", "цена без скидки"]):
                    if not explicit_25_col:
                        explicit_25_col = col

            min_valid = min(10, max(2, int(len(df) * 0.1)))
            price_col_indices = []
            for idx, col in enumerate(raw_cols):
                if name_col_idx is not None and idx <= name_col_idx:
                    continue
                c_str = str(col).lower().replace("–", "-").replace("—", "-").replace("−", "-").strip()
                if any(x in c_str for x in ["заказ", "орг. уп", "орг.уп", "произ.", "производитель", "годности", "годность", "остаток", "наличие"]):
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

            if explicit_25_col and explicit_100_col:
                p25_col = explicit_25_col
                p100_col = explicit_100_col
            elif explicit_100_col and price_col_indices:
                p25_col = raw_cols[price_col_indices[0]]
                p100_col = explicit_100_col
            elif len(price_col_indices) >= 2:
                p25_col = raw_cols[price_col_indices[0]]
                p100_col = raw_cols[price_col_indices[-1]]
            elif price_col_indices:
                p25_col = raw_cols[price_col_indices[0]]
                p100_col = raw_cols[price_col_indices[0]]
            else:
                p25_col = pick_price_column(raw_cols, price_c)
                p100_col = p25_col

        print(f"RESULT -> name_col: '{name_col}', p25_col: '{p25_col}', p100_col: '{p100_col}'")
    except Exception as ex:
        print("ERROR processing file:", ex)
