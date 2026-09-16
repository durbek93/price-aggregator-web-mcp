# -*- coding: utf-8 -*-
import os
import re
import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserSettings, CatalogItem, FileRecord
from app.schemas import CatalogItemSchema, SynonymSuggestionSchema
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/catalog", tags=["catalog"])

BASE_CATALOGS_DIR = Path(__file__).parent / "base_catalogs"
BASE_CATALOGS_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_CATALOG_FILE = Path(__file__).parent / "default_catalog.json"

def get_exclusive_brand_target(norm_name: str) -> Optional[str]:
    """Возвращает каноническое название для разделения форм анаферона, тенотена и ренгалина."""
    if re.search(r'(?:^|[\s\-_/(\[])(?:сдк|sdk)(?:$|[\s\-_/)\]])', norm_name):
        return None

    if "анаферон" in norm_name:
        if "капл" in norm_name or "25мл" in norm_name:
            return "Анаферон капли (детские) 25мл"
        if "взрос" in norm_name or "для взрос" in norm_name or "д/взр" in norm_name:
            return "Анаферон взрослый таб №20"
        if "дет" in norm_name:
            return "Анаферон детский таб №20"
        return "Анаферон взрослый таб №20"
        
    if "тенотен" in norm_name:
        if "дет" in norm_name or "д/дет" in norm_name:
            return "Тенотен детский таб №40"
        return "Тенотен таб №40"
        
    if "ренгалин" in norm_name:
        if "раствор" in norm_name or "r-r" in norm_name or "100мл" in norm_name or "сироп" in norm_name:
            return "Ренгалин раствор №1"
        return "Ренгалин таб. №20"
        
    return None


@router.get("", response_model=List[CatalogItemSchema])
def get_catalog(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Возвращает список элементов каталога (канонические имена и синонимы)."""
    return db.query(CatalogItem).filter(CatalogItem.user_id == current_user.id).all()


@router.post("", response_model=CatalogItemSchema)
def create_catalog_item(
    item_data: CatalogItemSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Добавляет новый элемент в каталог."""
    new_item = CatalogItem(
        user_id=current_user.id,
        canonical=item_data.canonical,
        aliases=item_data.aliases
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.put("/{item_id}", response_model=CatalogItemSchema)
def update_catalog_item(
    item_id: int,
    item_data: CatalogItemSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Обновляет элемент каталога."""
    item = db.query(CatalogItem).filter(CatalogItem.id == item_id, CatalogItem.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Элемент каталога не найден")
    
    item.canonical = item_data.canonical
    item.aliases = item_data.aliases
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_catalog_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаляет элемент каталога."""
    item = db.query(CatalogItem).filter(CatalogItem.id == item_id, CatalogItem.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Элемент каталога не найден")
    db.delete(item)
    db.commit()
    return {"message": "Элемент каталога успешно удален"}


@router.get("/base-catalogs", response_model=List[str])
def get_base_catalogs():
    """Возвращает список доступных базовых каталогов на сервере."""
    BASE_CATALOGS_DIR.mkdir(parents=True, exist_ok=True)
    files = list(BASE_CATALOGS_DIR.glob("*.json"))
    names = ["Материа Медика (По умолчанию)"]
    for f in files:
        name = f.stem
        if name not in names:
            names.append(name)
    return names


@router.post("/import-default")
def import_default_catalog(
    name: str = "Материа Медика (По умолчанию)",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Импортирует базовый каталог лекарств и синонимов для пользователя по имени."""
    # Удаляем старые записи каталога этого пользователя
    db.query(CatalogItem).filter(CatalogItem.user_id == current_user.id).delete()
    
    name = name.strip()
    if name == "Материа Медика (По умолчанию)":
        default_catalog = get_hardcoded_default_catalog()
    else:
        clean_name = "".join(c for c in name if c.isalnum() or c in " ._-()").strip()
        file_path = BASE_CATALOGS_DIR / f"{clean_name}.json"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Базовый каталог не найден")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                default_catalog = json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Не удалось прочитать базовый каталог: {str(e)}")
    
    for item in default_catalog:
        new_item = CatalogItem(
            user_id=current_user.id,
            canonical=item["canonical"],
            aliases=item["aliases"]
        )
        db.add(new_item)
        
    db.commit()
    return {"message": "Базовый каталог успешно импортирован"}


@router.post("/save-as-default")
def save_as_default_catalog(
    name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Сохраняет текущий каталог пользователя в качестве базового каталога с указанным именем."""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Имя каталога не может быть пустым")
        
    # Очищаем имя от нежелательных символов для создания безопасного файла
    clean_name = "".join(c for c in name if c.isalnum() or c in " ._-()").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Недопустимое имя каталога")
        
    items = db.query(CatalogItem).filter(CatalogItem.user_id == current_user.id).all()
    catalog_data = [
        {
            "canonical": item.canonical,
            "aliases": item.aliases
        }
        for item in items
    ]
    
    BASE_CATALOGS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = BASE_CATALOGS_DIR / f"{clean_name}.json"
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось сохранить базовый каталог: {str(e)}")
        
    return {"message": f"Каталог '{clean_name}' успешно сохранен в качестве базового на сервере"}


def get_hardcoded_default_catalog() -> List[dict]:
    return [
        {
            "canonical": "Анаферон детский таб №20",
            "aliases": [
                "анаферон дет", "анаф дет", "анаферон детский таб", "анаферон детский таб n20",
                "анаферон детский таб. №20", "анаферон таб. детские №20", "анаферон таб. детск. №20",
                "анаферон таб детск", "анаферон таб детские n20", "АНАФЕРОН ДЕТСКИЙ ТАБ №20",
                "АНАФЕРОН ДЕТС. ТАБ №20", "Анаферон детский №20", "Анаферон детский таб. №20 !!!",
                "Анаферон таб №20", "Анаферон детский капли 25мл", "Анаферон Детский капли 25мл", "Анаферон таб. №20"
            ]
        },
        {
            "canonical": "Анаферон взрослый таб №20",
            "aliases": [
                "Анаферон взрос. №20", "АНАФЕРОН №20 Д/ВЗР", "Анаферон таб. Взр №20", "анаферон таб",
                "Анаферон взр таб №20 !!!", "Анаферон взр таб №20", "анаферон взрослый", "анаферон таб. №20",
                "АНАФЕРОН ДЛЯ ВЗРОС  ТАБ N20", "анаферон для взрос", "анаферон для взрослых", "анаферон взр таб n20",
                "Анаферон таб №20,"
            ]
        },
        {
            "canonical": "Анаферон капли (детские) 25мл",
            "aliases": [
                "Анаферон детский капли 25мл.", "Анаферон детск капли для п/внутрь 25мл гомеоп", "Анаферон детский капли 25мл",
                "Анаферон детский капли гомеоп. д/приема внутрь 25мл ", "Анаферон детский капли д/приема внутрь 25мл",
                "анаферон капли", "анаферон капли дет", "анаферон капли 25", "анаферон капли (детские) 25мл",
                "анаферон детский капли", "анаферон капли д/детей 25мл", "Анаферон Детский капли 25мл",
                "Анаферон детский капли д/детей 25мл", "Анаферон детский  капли для п/внутрь 25мл",
                "Анаферон детский капли д/п/внутрь 25мл", "АНАФЕРОН ДЕТСКИЙ 25МЛ КАПЛИ N1",
                "Анаферон капли дет. 25мл", "Анаферон детс капли 25мл №1", "Анаферон детский  капли для п/внутрь гомеопатич, 25мл №1"
            ]
        },
        {
            "canonical": "Эргоферон таб №20",
            "aliases": [
                "эргоферон таб", "эргоферон таб. №20", "ЭРГОФЕРОН ТАБ №20",
                "Эргоферон таб. №20***", "Эргоферон таб. №20 Русс"
            ]
        },
        {
            "canonical": "Ренгалин таб. №20",
            "aliases": [
                "ренгалин таб", "ренгалин таб. №20", "Ренгалин таб.№20", "РЕНГАЛИН  ТАБ N20",
                "Ренгалин таб. д/рассас №20", "Ренгалин  таб. гомеоп. № 20",
                "РЕНГАЛИН ТАБ ГОМЕОПАТ. №20 Д/РАССАСЫВ."
            ]
        },
        {
            "canonical": "Ренгалин раствор №1",
            "aliases": [
                "Ренгалин р-р д/внутр. прим.100мл", "Ренгалин р-р. 100мл №1", "Ренгалин р-р для прием.внутрь гомеоп. 100мл",
                "Ренгалин р-р д/приёма внутрь 100мл ", "Ренгалин р-р 100мл №1", "ренгалин раствор",
                "РЕНГАЛИН Р-Р Д/ПРИЕМА ВНУТРЬ ГОМЕО-Е 100МЛ", "Ренгалин р-р д/пр внут гомеоп  100мл", "ренгалин 100",
                "ренгалин сироп", "Ренгалин р-р д/прием. внутрь 100мл", "Ренгалин р-р д/пр внут 100мл",
                "Ренгалин р-р д/пр. внутрь гомеоп. 100мл", "РЕНГАЛИН РАСТВОР 100МЛ  N1", "Ренгалин раствор 100мл",
                "РЕНГАЛИН Раствор внутрь 100мл", "Ренгалин раствор д/приема внутрь 100 мл", "Ренгалин 100мл"
            ]
        },
        {
            "canonical": "Тенотен таб №40",
            "aliases": [
                "тенотен таб. №40", "тенотен таб n40", "ТЕНОТЕН ВЗРОС  ТАБ N40",
                "тенотен взр таб", "тенотен взр", "тенотен взрос",
                "тенотен таб. д/рассас", "тенотен таб д/рассас", "тенотен таб д рассас",
                "Тенотен таб. №40***", "Тенотен взр таб №40", "Тенотен Взр таб. №40"
            ]
        },
        {
            "canonical": "Тенотен детский таб №40",
            "aliases": [
                "Тенотен-Детский таб.№40", "тенотен дет", "тенотен таб детский", "тенотен таб. детский №40",
                "тенотен таб №40 д/детей", "тенотен таб. детс. №40", "Тенотен таб. детский №40",
                "ТЕНОТЕН ДЕТСКИЙ  ТАБ N40", "Тенотен детский таб. №40", "Тенотен Детский таб. №40",
                "ТЕНОТЕН ДЕТСКИЙ ТАБ. №40", "Тенотен таб. детский №40***", "Тенотен детс таб №40",
                "Тенотен детский таб для рассасывания гомеопатические №40"
            ]
        },
        {
            "canonical": "Импаза №20",
            "aliases": ["ИМПАЗА №20", "импаза таб", "импаза таб. №20"]
        },
        {
            "canonical": "Афала №100",
            "aliases": [
                "афала №100", "афала таб №100", "афала таб. №100", "афала таб n100",
                "афала гомеопат таб n100", "афала гомеопат таб №100", "Афала таб №100", "АФАЛА ГОМЕОПАТ  ТАБ N100"
            ]
        },
        {
            "canonical": "Афалаза",
            "aliases": ["афалаза"]
        },
        {
            "canonical": "Климаксан таб. №20",
            "aliases": [
                "климаксан таб", "климаксан таб. №20", "Климаксан таб №20", "КЛИМАКСАН ТАБ. №20",
                "КЛИМАКСАН ТАБ №20 (ЙИГИРМАТТАЛИК)", "Климаксан таб №20!!"
            ]
        },
        {
            "canonical": "Климаксан Гранулы",
            "aliases": [
                "Климаксан гранулы 10г", "Климаксан грануль 10г", "КЛИМАКСАН ГРАН. 10Г",
                "КЛИМАКСАН ГОMЕОП ГРАН.10Г", "Климаксан гранулы 10г ."
            ]
        },
        {
            "canonical": "Млекоин гранулы 10г",
            "aliases": ["млекоин гранулы", "млекоин 10г", "МЛЕКОИН ГРАН.ГОМЕОП.10Г", "Млекоин гран гомеоп 10г"]
        },
        {
            "canonical": "Диваза",
            "aliases": ["диваза", "Диваза таб №100", "ДИВАЗА ТАБЛ ГОМЕОП. №100"]
        },
        {
            "canonical": "Успокой",
            "aliases": [
                "успокой", "УСПОКОЙ ТАБ №20", "Успокой таб. №20", "УСПОКОЙ ТАБЛ ГОМЕОП.№20",
                "Успокой таб. №20 (Успокоительное)", "УСПОКОЙ - гомеопатик таб. №20"
            ]
        },
        {
            "canonical": "Фарингомед",
            "aliases": ["фарингомед"]
        },
        {
            "canonical": "Колофорт таблетки",
            "aliases": ["Колофорт таб. №100"]
        }
    ]


@router.get("/suggest-synonyms", response_model=List[SynonymSuggestionSchema])
def suggest_synonyms(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Анализирует все загруженные прайсы и предлагает синонимы для каталога с учетом производителей и разделением форм."""
    import pandas as pd
    from rapidfuzz import fuzz
    from app.core.price_utils import normalize_name
    from app.core.svodny_price import pick_column
    
    # 1. Получаем настройки пользователя
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not user_settings:
        name_candidates = ["Препарат", "Наименование", "Наименование препарата", "Наименование товаров", "Наименование товара", "Наименование препаратов", "Товары", "Махсулот номи", "Номенклатура", "Товар", "Название", "Name", "Позиция"]
        target_producers = ["материа", "materia"]
        producer_candidates = ["Производитель", "Бренд", "Завод", "Фирма"]
    else:
        name_candidates = user_settings.columns.get("name_candidates", [])
        target_producers = [p.lower() for p in (user_settings.producers or ["материа", "materia"])]
        producer_candidates = user_settings.columns.get("producer_candidates", [])
        
    # Ключевые слова брендов для фолбека (если производителя нет в таблице)
    brand_keywords = ["анаферон", "эргоферон", "ренгалин", "тенотен", "импаза", "афала", "афалаза", "климаксан", "млекоин", "диваза", "успокой", "фарингомед"]
    
    # 2. Получаем все входные файлы пользователя
    input_files = db.query(FileRecord).filter(
        FileRecord.user_id == current_user.id,
        FileRecord.file_type == "input"
    ).all()
    
    # Извлекаем уникальные названия лекарств
    extracted_names = set()
    for f in input_files:
        if not os.path.exists(f.storage_path):
            continue
        try:
            df = None
            engine = "openpyxl"
            if str(f.storage_path).endswith(".xls"):
                engine = "xlrd"
                
            for header_row in range(15):
                try:
                    probe = pd.read_excel(f.storage_path, engine=engine, header=header_row, nrows=5)
                except Exception:
                    continue
                if len(probe.columns) < 2:
                    continue
                
                name_col = pick_column(list(probe.columns), name_candidates)
                if name_col:
                    producer_col = pick_column(list(probe.columns), producer_candidates)
                    
                    # Читаем только нужные колонки
                    cols_to_read = [name_col]
                    if producer_col:
                        cols_to_read.append(producer_col)
                        
                    df_full = pd.read_excel(f.storage_path, engine=engine, header=header_row, usecols=cols_to_read)
                    
                    for _, row in df_full.iterrows():
                        val_name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
                        if not val_name or len(val_name) <= 2 or val_name.isdigit():
                            continue
                            
                        # Проверяем производителя
                        is_target = False
                        if producer_col and pd.notna(row[producer_col]):
                            val_prod = str(row[producer_col]).strip().lower()
                            if any(tp in val_prod for tp in target_producers):
                                is_target = True
                                
                        # Если производителя не нашли в строке или колонка отсутствует,
                        # используем фолбек по ключевым словам бренда в названии
                        if not is_target:
                            norm_name = val_name.lower()
                            if any(bk in norm_name for bk in brand_keywords):
                                is_target = True
                                
                        if is_target:
                            extracted_names.add(val_name)
                    break
        except Exception:
            continue
            
    # 3. Загружаем каталог лекарств пользователя
    catalog_items = db.query(CatalogItem).filter(CatalogItem.user_id == current_user.id).all()
    if not catalog_items:
        return []
        
    # Создаем быстрый поиск по существующим элементам каталога (в нижнем регистре)
    existing_aliases = {}
    existing_canonicals = {}
    for item in catalog_items:
        norm_can = normalize_name(item.canonical)
        existing_canonicals[norm_can] = item
        for alias in item.aliases:
            norm_al = normalize_name(alias)
            existing_aliases[norm_al] = item
            
    suggestions = []
    
    # 4. Проверяем каждое извлеченное название
    for name in extracted_names:
        norm_name = normalize_name(name)
        if not norm_name:
            continue
            
        # Если название уже есть в каталоге (как каноническое или синоним), пропускаем его
        if norm_name in existing_aliases or norm_name in existing_canonicals:
            continue
            
        # Проверяем эксклюзивное разделение бренда
        exclusive_target = get_exclusive_brand_target(norm_name)
        
        best_match = None
        best_score = 0
        
        if exclusive_target:
            # Ищем конкретный элемент каталога с этим каноническим названием
            item = next((i for i in catalog_items if i.canonical == exclusive_target), None)
            if item:
                # Сравниваем только с этим элементом!
                best_score = fuzz.ratio(norm_name, normalize_name(item.canonical))
                best_match = item
                for alias in item.aliases:
                    score = fuzz.ratio(norm_name, normalize_name(alias))
                    if score > best_score:
                        best_score = score
                
        else:
            # Иначе сравниваем со всеми элементами каталога, КРОМЕ разделяемых брендов
            for item in catalog_items:
                if any(brand in normalize_name(item.canonical) for brand in ["анаферон", "тенотен", "ренгалин"]):
                    continue
                    
                # Сравниваем с каноническим названием
                score = fuzz.ratio(norm_name, normalize_name(item.canonical))
                if score > best_score:
                    best_score = score
                    best_match = item
                    
                # Сравниваем с каждым синонимом
                for alias in item.aliases:
                    score = fuzz.ratio(norm_name, normalize_name(alias))
                    if score > best_score:
                        best_score = score
                        best_match = item
                        
        # Если схожесть находится в диапазоне 55% - 95%, добавляем предложение
        if 55 <= best_score < 96 and best_match:
            suggestions.append({
                "suggested_alias": name,
                "canonical_id": best_match.id,
                "canonical_name": best_match.canonical,
                "confidence_score": round(best_score, 1)
            })
            
    # Сортируем по уверенности (схожести) и отдаем топ-50
    suggestions.sort(key=lambda x: x["confidence_score"], reverse=True)
    return suggestions[:50]
