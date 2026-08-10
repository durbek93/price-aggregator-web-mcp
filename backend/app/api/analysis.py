# -*- coding: utf-8 -*-
import os
import pandas as pd
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, FileRecord, UserSettings
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.get("/compare")
def compare_prices(
    date1: Optional[str] = None,
    date2: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Сравнивает цены двух сводных отчетов (по умолчанию двух последних или по указанным датам)."""
    # 1. Авто-обнаружение, синхронизация с диском и дедупликация
    from app.api.dependencies import auto_discover_user_files
    auto_discover_user_files(db, current_user.id)

    query = db.query(FileRecord).filter(
        FileRecord.user_id == current_user.id,
        FileRecord.file_type == "output",
        FileRecord.filename.like("%Сводный%")
    )

    if date1 and date2:
        file1 = query.filter(FileRecord.filename.like(f"%{date1}%")).first()
        file2 = query.filter(FileRecord.filename.like(f"%{date2}%")).first()

        if not file1 or not file2:
            all_outputs = query.order_by(FileRecord.uploaded_at.desc()).all()
            if not file1:
                file1 = next((f for f in all_outputs if date1 in f.filename or (f.uploaded_at and date1 in f.uploaded_at.strftime("%d.%m.%Y"))), None)
            if not file2:
                file2 = next((f for f in all_outputs if date2 in f.filename or (f.uploaded_at and date2 in f.uploaded_at.strftime("%d.%m.%Y"))), None)

        if file1 and file2:
            if file1.uploaded_at < file2.uploaded_at:
                current_file, previous_file = file2, file1
            else:
                current_file, previous_file = file1, file2
        else:
            output_files = query.order_by(FileRecord.uploaded_at.desc()).limit(2).all()
            current_file = output_files[0] if output_files else None
            previous_file = output_files[1] if len(output_files) > 1 else None
    else:
        output_files = query.order_by(FileRecord.uploaded_at.desc()).limit(2).all()
        if not output_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не найдено ни одного сгенерированного сводного прайс-листа"
            )
        current_file = output_files[0]
        previous_file = output_files[1] if len(output_files) > 1 else None

    if not current_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не найдено подходящих сводных прайс-листов для сравнения"
        )

    # Загружаем настройки пользователя (для списка производителей/препаратов)
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    producers = user_settings.producers if user_settings else []

    # Читаем текущий файл
    if not os.path.exists(current_file.storage_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Файл текущего сводного прайса не найден на сервере: {current_file.filename}"
        )

    def load_and_clean_df(path: str) -> pd.DataFrame:
        try:
            df = pd.read_excel(path, sheet_name="СвПрайс", header=3)
        except Exception as e:
            raise ValueError(f"Ошибка при чтении Excel: {str(e)}")
            
        if df.shape[1] == 18:
            first_col_val = str(df.columns[1]).lower()
            if "дистрибьютор" in first_col_val or "препарат" in first_col_val:
                mapping = {
                    0: "№",
                    1: "Препарат",
                    2: "Зента Фарм (25% предоплата)",
                    3: "Зента Фарм (100% предоплата)",
                    4: "Гранд Фарм (25% предоплата)",
                    5: "Гранд Фарм (100% предоплата)",
                    6: "Мерос Фарм (25% предоплата)",
                    7: "Мерос Фарм (100% предоплата)",
                    8: "Драг Промоушен (25% предоплата)",
                    9: "Драг Промоушен (100% предоплата)",
                    10: "Фарма Чойз",
                    11: "Биотек Фарм (25% предоплата)",
                    12: "Биотек Фарм (100% предоплата)",
                    13: "Фарм Люкс (25% предоплата)",
                    14: "Фарм Люкс (100% предоплата)",
                    15: "Аэро Фарм (25% предоплата)",
                    16: "Аэро Фарм (100% предоплата)",
                    17: "Дельфарм"
                }
                df.columns = [mapping.get(i, f"Col_{i}") for i in range(len(df.columns))]
                df = df[df["№"].notna()].copy()
                return df
                
        # Fallback
        try:
            df = pd.read_excel(path, sheet_name="СвПрайс", header=0)
        except Exception as e:
            raise ValueError(f"Ошибка при чтении Excel (fallback): {str(e)}")
            
        if "Препарат" not in df.columns:
            if len(df.columns) > 0:
                df.rename(columns={df.columns[0]: "Препарат"}, inplace=True)
        return df

    try:
        df_curr = load_and_clean_df(current_file.storage_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обработке текущего файла Excel: {str(e)}"
        )

    df_prev = None
    if previous_file and os.path.exists(previous_file.storage_path):
        try:
            df_prev = load_and_clean_df(previous_file.storage_path)
        except Exception as e:
            print(f"Error reading previous output file {previous_file.filename}: {e}")
            df_prev = None

    drugs_data = {}
    curr_suppliers = [col for col in df_curr.columns if col not in ["Препарат", "№", "No"]]

    # Идем по строкам текущего прайса
    for _, row in df_curr.iterrows():
        drug_name = str(row["Препарат"]).strip()
        if not drug_name or drug_name == "nan":
            continue

        # Собираем все текущие предложения по этому препарату
        offers = []
        for supplier in curr_suppliers:
            price = row[supplier]
            # Проверяем, что цена числовая и не NaN
            if pd.notna(price) and isinstance(price, (int, float)) and price > 0:
                offers.append({"supplier": supplier, "price": float(price)})

        # Если по препарату нет ни одной цены, пропускаем его
        if not offers:
            continue

        # Сортируем предложения и берем топ-3 лучших
        offers_sorted = sorted(offers, key=lambda x: x["price"])
        best_offers = offers_sorted[:3]

        dynamics = []
        status_str = "stable"
        deficit_details = None
        disappeared_suppliers = []

        # Считаем динамику, если есть с чем сравнивать
        if df_prev is not None and "Препарат" in df_prev.columns:
            # Находим эту позицию в прошлом прайсе
            prev_row_match = df_prev[df_prev["Препарат"].str.strip() == drug_name]
            if not prev_row_match.empty:
                prev_row = prev_row_match.iloc[0]
                prev_suppliers = [col for col in df_prev.columns if col != "Препарат"]

                # Для каждого поставщика из текущего прайса считаем дельту
                for supplier in curr_suppliers:
                    curr_price = row[supplier]
                    if supplier in prev_row:
                        prev_price = prev_row[supplier]
                        
                        # Если цена была и есть сейчас, считаем изменение
                        if pd.notna(curr_price) and pd.notna(prev_price) and prev_price > 0:
                            change = float(curr_price) - float(prev_price)
                            pct = round((change / float(prev_price)) * 100, 1)
                            dynamics.append({
                                "supplier": supplier,
                                "change_uzs": float(change),
                                "change_percent": pct
                            })
                    
                # Ищем поставщиков, у которых товар пропал (был в прошлом, нет в текущем)
                for supplier in prev_suppliers:
                    prev_price = prev_row[supplier]
                    if pd.notna(prev_price) and float(prev_price) > 0:
                        if supplier not in row or pd.isna(row[supplier]) or float(row[supplier]) <= 0:
                            disappeared_suppliers.append(supplier)

        if disappeared_suppliers:
            status_str = "deficit"
            deficit_details = f"Позиция вымылась у дистрибьюторов: {', '.join(disappeared_suppliers)}"

        drugs_data[drug_name] = {
            "best_offers": best_offers,
            "dynamics": dynamics,
            "status": status_str,
        }
        if deficit_details:
            drugs_data[drug_name]["deficit_details"] = deficit_details

    return {
        "meta": {
            "current_file": current_file.filename,
            "previous_file": previous_file.filename if previous_file else None,
            "producers": producers
        },
        "drugs": drugs_data
    }


@router.get("/manufacturer-compare")
def compare_manufacturer_prices(
    producer: str,
    days: int = 3,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Сравнивает цены дистрибьюторов на препараты конкретного производителя за последние N дней."""
    from datetime import datetime, timedelta
    from pathlib import Path
    from app.api.dependencies import auto_discover_user_files
    from app.defaults import DEFAULT_COLUMNS
    from app.core.svodny_price import friendly_source_label, read_price_table, extract_by_producer, normalize_product_for_grouping

    # 1. Синхронизируем файлы
    auto_discover_user_files(db, current_user.id)
    
    # 2. Ищем все файлы input и input_history за последние N дней
    time_limit = datetime.utcnow() - timedelta(days=days)
    files = db.query(FileRecord).filter(
        FileRecord.user_id == current_user.id,
        FileRecord.file_type.in_(["input", "input_history"]),
        FileRecord.uploaded_at >= time_limit
    ).order_by(FileRecord.uploaded_at.desc()).all()
    
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не найдено прайс-листов дистрибьюторов за последние {days} дней."
        )

    # Загружаем настройки пользователя (для определения кандидатов колонок)
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    columns_config = user_settings.columns if user_settings else DEFAULT_COLUMNS
    
    key_cands = columns_config.get("key_candidates", [])
    name_cands = columns_config.get("name_candidates", [])
    price_cands = columns_config.get("price_candidates", [])
    stock_cands = columns_config.get("stock_candidates", [])
    prod_cands = columns_config.get("producer_candidates", [])

    all_extracted_rows = []
    
    for f in files:
        if not os.path.exists(f.storage_path):
            continue
            
        distributor = friendly_source_label(f.filename)
        
        try:
            # Читаем файл в DataFrame
            df = read_price_table(
                path=Path(f.storage_path),
                key_candidates=key_cands,
                name_candidates=name_cands,
                price_candidates=price_cands,
                stock_candidates=stock_cands,
                use_key=False,
                use_name=True,
                read_preset=f.read_preset or None
            )
            
            # Извлекаем строки для нужного производителя
            rows = extract_by_producer(
                df=df,
                path=Path(f.storage_path),
                producer_substrings=[producer],
                key_candidates=key_cands,
                name_candidates=name_cands,
                price_candidates=price_cands,
                stock_candidates=stock_cands,
                producer_candidates=prod_cands
            )
            
            # Сохраняем информацию
            for row in rows:
                row["distributor"] = distributor
                row["uploaded_at"] = f.uploaded_at.isoformat()
                row["file_id"] = f.id
                all_extracted_rows.append(row)
                
        except Exception as e:
            # Логируем и пропускаем сбойные файлы
            print(f"Error parsing file {f.filename} for manufacturer analysis: {e}")

    if not all_extracted_rows:
        return {
            "meta": {
                "producer": producer,
                "days": days,
                "total_files_analyzed": len(files),
                "analyzed_files": [f.filename for f in files]
            },
            "drugs": {}
        }

    # 1. Найдем время последнего импорта для каждого дистрибьютора
    latest_upload_time = {}
    for f in files:
        dist = friendly_source_label(f.filename)
        if dist not in latest_upload_time or f.uploaded_at > latest_upload_time[dist]:
            latest_upload_time[dist] = f.uploaded_at

    # 2. Группируем предложения
    grouped_data = {}
    
    for row in all_extracted_rows:
        raw_name = row["name"]
        norm_name = normalize_product_for_grouping(raw_name)
        dist = row["distributor"]
        price = row["price"]
        dt = datetime.fromisoformat(row["uploaded_at"])
        
        if norm_name not in grouped_data:
            grouped_data[norm_name] = {
                "display_name": raw_name,
                "distributors": {}
            }
        
        dist_history = grouped_data[norm_name]["distributors"].setdefault(dist, [])
        dist_history.append({
            "date": dt,
            "price": price,
            "raw_name": raw_name
        })

    # 3. Анализируем динамику, дефицит и новинки для каждого препарата
    drugs_analysis = {}
    
    for norm_name, info in grouped_data.items():
        display_name = info["display_name"]
        distributors_info = {}
        
        for dist, history in info["distributors"].items():
            # Сортируем историю по дате по возрастанию
            history_sorted = sorted(history, key=lambda x: x["date"])
            
            # Определяем текущую (последнюю) цену у этого дистрибьютора
            latest_entry = history_sorted[-1]
            latest_price = latest_entry["price"]
            
            # Проверим, является ли эта запись последней по времени загрузки этого дистрибьютора
            is_currently_active = (latest_entry["date"] == latest_upload_time[dist])
            
            # Вычисляем изменение цены
            change_uzs = 0.0
            change_percent = 0.0
            
            if len(history_sorted) > 1:
                prev_entry = history_sorted[-2]
                prev_price = prev_entry["price"]
                change_uzs = latest_price - prev_price
                if prev_price > 0:
                    change_percent = round((change_uzs / prev_price) * 100, 1)
            
            # Определяем статус
            status_str = "stable"
            if not is_currently_active:
                status_str = "deficit"
            elif len(history_sorted) == 1 and len(files) > 1:
                dist_files_count = sum(1 for f in files if friendly_source_label(f.filename) == dist)
                if dist_files_count > 1:
                    status_str = "new"
            elif change_uzs > 0:
                status_str = "increased"
            elif change_uzs < 0:
                status_str = "decreased"
                
            distributors_info[dist] = {
                "current_price": latest_price if is_currently_active else None,
                "history": [
                    {"date": h["date"].isoformat(), "price": h["price"]}
                    for h in history_sorted
                ],
                "change_uzs": change_uzs if is_currently_active else 0.0,
                "change_percent": change_percent if is_currently_active else 0.0,
                "status": status_str,
                "last_seen_date": latest_entry["date"].isoformat()
            }
            
        drugs_analysis[display_name] = {
            "distributors": distributors_info
        }

    return {
        "meta": {
            "producer": producer,
            "days": days,
            "total_files_analyzed": len(files),
            "analyzed_files": [f.filename for f in files]
        },
        "drugs": drugs_analysis
    }


def stem_word(w: str) -> str:
    w = w.lower().strip()
    if len(w) > 4:
        suffixes = ["ами", "ями", "ого", "его", "ому", "ему", "ом", "ем", "ам", "ям", "ах", "ях", "ов", "ев", "ей", "а", "я", "о", "е", "у", "ю", "ы", "и"]
        for suffix in suffixes:
            if w.endswith(suffix) and len(w) - len(suffix) >= 4:
                return w[:-len(suffix)]
    return w


@router.get("/drug-compare")
def compare_drug_prices(
    drug: str,
    days: int = 3,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Сравнивает цены дистрибьюторов на конкретный препарат за последние N дней."""
    from datetime import datetime, timedelta
    from pathlib import Path
    from app.api.dependencies import auto_discover_user_files
    from app.defaults import DEFAULT_COLUMNS
    from app.core.svodny_price import (
        friendly_source_label,
        read_price_table,
        normalize_product_for_grouping,
        is_excluded_product,
        pick_column,
        resolve_price_column_for_sheet,
        normalize_name,
        to_number,
        round_price
    )

    # 1. Синхронизируем файлы
    auto_discover_user_files(db, current_user.id)
    
    # 2. Ищем все файлы input и input_history за последние N дней
    time_limit = datetime.utcnow() - timedelta(days=days)
    all_files = db.query(FileRecord).filter(
        FileRecord.user_id == current_user.id,
        FileRecord.file_type.in_(["input", "input_history"]),
        FileRecord.uploaded_at >= time_limit
    ).order_by(FileRecord.uploaded_at.desc()).all()
    
    if not all_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не найдено прайс-листов дистрибьюторов за последние {days} дней."
        )

    # Дедупликация: берем только 1 последний прайс для каждого дистрибьютора в рамках одной даты
    seen_keys = set()
    files = []
    for f in all_files:
        date_str = f.uploaded_at.strftime("%Y-%m-%d")
        dist = friendly_source_label(f.filename)
        key = (dist, date_str)
        if key not in seen_keys:
            seen_keys.add(key)
            files.append(f)

    # Загружаем настройки
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    columns_config = user_settings.columns if user_settings else DEFAULT_COLUMNS
    
    key_cands = columns_config.get("key_candidates", [])
    name_cands = columns_config.get("name_candidates", [])
    price_cands = columns_config.get("price_candidates", [])
    stock_cands = columns_config.get("stock_candidates", [])
    prod_cands = columns_config.get("producer_candidates", [])

    # Подготавливаем части поискового запроса с усечением падежных окончаний
    raw_query_parts = [p.lower() for p in normalize_name(drug).split() if p.strip()]
    if not raw_query_parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поисковый запрос препарата пуст или некорректен."
        )
    stemmed_query_parts = [stem_word(p) for p in raw_query_parts]

    all_extracted_rows = []
    
    for f in files:
        if not os.path.exists(f.storage_path):
            continue
            
        distributor = friendly_source_label(f.filename)
        
        try:
            df = read_price_table(
                path=Path(f.storage_path),
                key_candidates=key_cands,
                name_candidates=name_cands,
                price_candidates=price_cands,
                stock_candidates=stock_cands,
                use_key=False,
                use_name=True,
                read_preset=f.read_preset or None
            )
            
            # Фильтруем строки по названию препарата напрямую
            name_col = pick_column(list(df.columns), name_cands)
            price_col = resolve_price_column_for_sheet(df, Path(f.storage_path), price_cands)
            key_col = pick_column(list(df.columns), key_cands)
            producer_col = pick_column(list(df.columns), prod_cands)
            
            if not name_col or not price_col:
                continue
                
            for _, r in df.iterrows():
                name_val = r.get(name_col)
                if name_val is None or (isinstance(name_val, float) and pd.isna(name_val)):
                    continue
                if is_excluded_product(str(name_val)):
                    continue
                    
                name_norm = normalize_name(str(name_val))
                name_words = name_norm.split()
                stemmed_name_words = [stem_word(w) for w in name_words]
                full_stemmed_name = " ".join(stemmed_name_words)

                # Проверяем, что ВСЕ поисковые слова (или их основы) содержатся в названии препарата
                match_ok = True
                for sqp, raw_p in zip(stemmed_query_parts, raw_query_parts):
                    if not (raw_p in name_norm or sqp in full_stemmed_name or any(sqp in sw or sw in sqp for sw in stemmed_name_words)):
                        match_ok = False
                        break

                if not match_ok:
                    continue
                    
                price = to_number(r.get(price_col))
                rounded_price = round_price(price)
                if rounded_price is None:
                    continue
                    
                producer_val = r.get(producer_col) if producer_col else ""
                
                all_extracted_rows.append({
                    "key": r.get(key_col),
                    "name": str(name_val),
                    "price": rounded_price,
                    "producer": str(producer_val or ""),
                    "distributor": distributor,
                    "uploaded_at": f.uploaded_at.isoformat(),
                    "file_id": f.id
                })
                
        except Exception as e:
            print(f"Error parsing file {f.filename} for drug analysis: {e}")

    if not all_extracted_rows:
        return {
            "meta": {
                "drug": drug,
                "days": days,
                "total_files_analyzed": len(files),
                "analyzed_files": [f.filename for f in files]
            },
            "drugs": {}
        }

    # 1. Найдем время последнего импорта для каждого дистрибьютора
    latest_upload_time = {}
    for f in files:
        dist = friendly_source_label(f.filename)
        if dist not in latest_upload_time or f.uploaded_at > latest_upload_time[dist]:
            latest_upload_time[dist] = f.uploaded_at

    # 2. Группируем предложения по препаратам
    grouped_data = {}
    
    for row in all_extracted_rows:
        raw_name = row["name"]
        norm_name = normalize_product_for_grouping(raw_name)
        dist = row["distributor"]
        price = row["price"]
        dt = datetime.fromisoformat(row["uploaded_at"])
        
        if norm_name not in grouped_data:
            grouped_data[norm_name] = {
                "display_name": raw_name,
                "producer": row["producer"],
                "distributors": {}
            }
        
        dist_history = grouped_data[norm_name]["distributors"].setdefault(dist, [])
        dist_history.append({
            "date": dt,
            "price": price,
            "raw_name": raw_name
        })

    # 3. Анализируем динамику, дефицит и новинки
    drugs_analysis = {}
    
    for norm_name, info in grouped_data.items():
        display_name = info["display_name"]
        distributors_info = {}
        
        for dist, history in info["distributors"].items():
            history_sorted = sorted(history, key=lambda x: x["date"])
            latest_entry = history_sorted[-1]
            latest_price = latest_entry["price"]
            
            is_currently_active = (latest_entry["date"] == latest_upload_time[dist])
            
            change_uzs = 0.0
            change_percent = 0.0
            
            if len(history_sorted) > 1:
                prev_entry = history_sorted[-2]
                prev_price = prev_entry["price"]
                change_uzs = latest_price - prev_price
                if prev_price > 0:
                    change_percent = round((change_uzs / prev_price) * 100, 1)
            
            status_str = "stable"
            if not is_currently_active:
                status_str = "deficit"
            elif len(history_sorted) == 1 and len(files) > 1:
                dist_files_count = sum(1 for f in files if friendly_source_label(f.filename) == dist)
                if dist_files_count > 1:
                    status_str = "new"
            elif change_uzs > 0:
                status_str = "increased"
            elif change_uzs < 0:
                status_str = "decreased"
                
            distributors_info[dist] = {
                "current_price": latest_price if is_currently_active else None,
                "history": [
                    {"date": h["date"].isoformat(), "price": h["price"]}
                    for h in history_sorted
                ],
                "change_uzs": change_uzs if is_currently_active else 0.0,
                "change_percent": change_percent if is_currently_active else 0.0,
                "status": status_str,
                "last_seen_date": latest_entry["date"].isoformat()
            }
            
        drugs_analysis[display_name] = {
            "producer": info["producer"],
            "distributors": distributors_info
        }

    return {
        "meta": {
            "drug": drug,
            "days": days,
            "total_files_analyzed": len(files),
            "analyzed_files": [f.filename for f in files]
        },
        "drugs": drugs_analysis
    }


@router.get("/system-summary")
def get_system_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает общую сводку о загруженных прайсах, сводных отчетах и каталоге для ИИ-агента."""
    from app.api.dependencies import auto_discover_user_files
    from app.models import CatalogItem

    auto_discover_user_files(db, current_user.id)

    output_files = db.query(FileRecord).filter(
        FileRecord.user_id == current_user.id,
        FileRecord.file_type == "output"
    ).order_by(FileRecord.uploaded_at.desc()).limit(20).all()

    input_files = db.query(FileRecord).filter(
        FileRecord.user_id == current_user.id,
        FileRecord.file_type == "input"
    ).order_by(FileRecord.uploaded_at.desc()).all()

    catalog_count = db.query(CatalogItem).filter(CatalogItem.user_id == current_user.id).count()

    output_summary = [
        {
            "id": f.id,
            "filename": f.display_name or f.filename,
            "size_kb": round(f.file_size / 1024, 1),
            "uploaded_at": f.uploaded_at.strftime("%Y-%m-%d %H:%M") if f.uploaded_at else None
        }
        for f in output_files
    ]

    input_summary = [
        {
            "id": f.id,
            "filename": f.display_name or f.filename,
            "read_preset": f.read_preset,
            "uploaded_at": f.uploaded_at.strftime("%Y-%m-%d %H:%M") if f.uploaded_at else None
        }
        for f in input_files
    ]

    # 3. Файлы отчетов по продажам (папка sales)
    from pathlib import Path
    from app.config import settings
    sales_dir = settings.OUTPUT_DIR / "sales"
    sales_files = []
    if sales_dir.exists():
        sales_files = [f.name for f in sales_dir.glob("*.xlsx")]

    return {
        "user_id": current_user.id,
        "total_input_files": len(input_files),
        "total_output_files": len(output_files),
        "total_sales_files": len(sales_files),
        "sales_files": sales_files,
        "catalog_items_count": catalog_count,
        "latest_output_reports": output_summary,
        "uploaded_input_prices": input_summary
    }


@router.get("/sales-compare")
def compare_sales_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Агрегирует данные о продажах пользователя из директории outputs/{user_id}/sales/."""
    from pathlib import Path
    from app.config import settings
    from app.api.dependencies import auto_discover_user_files
    from app.core.sales_parser import aggregate_sales_data

    # Синхронизируем обнаружение файлов
    auto_discover_user_files(db, current_user.id)

    sales_dir = settings.OUTPUT_DIR / str(current_user.id) / "sales"
    data = aggregate_sales_data(sales_dir)

    if data.get("summary", {}).get("total_realization", 0) == 0 and data.get("summary", {}).get("total_units", 0) == 0:
        # Резервная проверка 1: outputs/sales/
        shared_sales_dir = settings.OUTPUT_DIR / "sales"
        if shared_sales_dir.exists():
            data = aggregate_sales_data(shared_sales_dir)

    if data.get("summary", {}).get("total_realization", 0) == 0 and data.get("summary", {}).get("total_units", 0) == 0:
        # Резервная проверка 2: если файлы лежат в корне outputs/{user_id} или outputs/
        root_outputs_dir = settings.OUTPUT_DIR / str(current_user.id)
        if root_outputs_dir.exists():
            for f in root_outputs_dir.glob("*.xlsx"):
                data = aggregate_sales_data(root_outputs_dir)
                break

    return data


