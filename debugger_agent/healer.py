# -*- coding: utf-8 -*-
import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
import google.generativeai as genai

import config
from auditor import Discrepancy

logger = logging.getLogger("debugger_agent.healer")

if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)


@dataclass
class ProposedFix:
    fix_id: str
    distributor_key: str
    distributor_label: str
    raw_filename: str
    issue_summary: str
    root_cause: str
    proposed_rule: Dict[str, Any]
    explanation: str


async def diagnose_and_propose_fix(discrepancy: Discrepancy) -> ProposedFix:
    """
    Uses Gemini LLM to inspect raw distributor file structure and generate an accurate parsing fix.
    """
    sample_data = discrepancy.raw_sample_data
    columns = sample_data.get("columns", [])
    numeric_cols = sample_data.get("numeric_price_cols", [])
    sample_row = sample_data.get("sample_row", {})

    prompt = f"""
Ты эксперт по анализу прайс-листов фармацевтических дистрибьюторов.
Произошла ошибка при сборке сводного прайс-листа:
Дистрибьютор: {discrepancy.distributor_label}
Файл: {discrepancy.raw_filename}
Тип проблемы: {discrepancy.issue_type}
Описание: {discrepancy.description}
Препарат в прайсе: {sample_data.get('raw_product_name', 'Не указан')}
Целевой препарат в шаблоне: {sample_data.get('target_template_product', 'Не указан')}

Список колонок в файле дистрибьютора:
{columns}

Колонки с числовыми ценами (>500):
{numeric_cols}

Пример строки с препаратом:
{json.dumps({k: str(v) for k, v in sample_row.items()}, ensure_ascii=False, indent=2)}

Задача:
1. Определи причину сбоя (почему стандартный парсер не сопоставил препарат или пропустил нужную колонку).
2. Выбери точные имена колонок:
   - name_col: колонка с наименованием препарата
   - p25_col: колонка с базовой ценой (25% оплата / отсрочка)
   - p100_col: колонка со 100% предоплатой (максимальная скидка, например -4%, -3%, Цена 100% и т.д.)
3. Дай краткое и понятное объяснение проблемы и решения на русском языке (для сообщения в Telegram).

Ответь СТРОГО в формате валидного JSON:
{{
  "root_cause": "Краткая причина (1-2 предложения)",
  "name_col": "Название_колонки_наименования",
  "p25_col": "Название_колонки_базовой_цены",
  "p100_col": "Название_колонки_скидочной_цены",
  "explanation": "Понятное для пользователя описание проблемы и что предлагается исправить"
}}
"""

    fix_id = f"{discrepancy.distributor_key}_{abs(hash(discrepancy.raw_filename + str(sample_data.get('raw_product_name', '')))) % 10000}"
    
    # Heuristic fallback if LLM is unavailable or fails
    fallback_p25 = numeric_cols[0] if numeric_cols else "Цена"
    fallback_p100 = numeric_cols[-1] if numeric_cols else fallback_p25
    fallback_name = "Наименование"
    for c in columns:
        if any(k in str(c).lower() for k in ["наименование", "название", "товар"]):
            fallback_name = str(c)
            break

    try:
        if config.GEMINI_API_KEY:
            model = genai.GenerativeModel(config.GEMINI_MODEL)
            response = await model.generate_content_async(
                prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.1}
            )
            data = json.loads(response.text)
            
            root_cause = data.get("root_cause", "Изменение структуры таблицы дистрибьютора.")
            name_col = data.get("name_col") or fallback_name
            p25_col = data.get("p25_col") or fallback_p25
            p100_col = data.get("p100_col") or fallback_p100
            explanation = data.get("explanation", f"Назначить p25='{p25_col}', p100='{p100_col}'")
            
            def _match_existing_col(target: Optional[str]) -> Optional[str]:
                if not target:
                    return None
                tgt_s = str(target).strip().lower()
                if tgt_s.startswith("unnamed"):
                    return None
                for c in columns:
                    c_s = str(c).strip().lower()
                    if c_s.startswith("unnamed"):
                        continue
                    if c_s == tgt_s:
                        return str(c)
                for c in columns:
                    c_s = str(c).strip().lower()
                    if c_s.startswith("unnamed"):
                        continue
                    if "".join(c_s.split()) == "".join(tgt_s.split()):
                        return str(c)
                return None

            # Validate that columns returned by LLM actually exist in the raw file
            matched_name = _match_existing_col(name_col)
            name_col = matched_name if matched_name else fallback_name

            matched_p25 = _match_existing_col(p25_col)
            matched_p100 = _match_existing_col(p100_col)

            # Filter detected numeric price columns to exclude Unnamed
            valid_num_cols = [c for c in numeric_cols if not str(c).strip().lower().startswith("unnamed")]

            # If LLM proposed non-existent columns, fall back to detected numeric price columns
            if p25_col and not matched_p25:
                matched_p25 = valid_num_cols[0] if valid_num_cols else None
            if p100_col and not matched_p100:
                matched_p100 = valid_num_cols[-1] if valid_num_cols else matched_p25

            p25_col = matched_p25
            p100_col = matched_p100

            # Multi-file distributors should never have identical p25 and p100 mapped from a single file
            is_multi = discrepancy.distributor_key in ["grand", "promotion", "luxe"]
            if is_multi and p25_col and p25_col == p100_col:
                if "100" in discrepancy.raw_filename.lower():
                    p25_col = None
                else:
                    p100_col = None
            elif discrepancy.distributor_key == "biotek" and p25_col and p100_col and p25_col == p100_col:
                # For Biotek, if price columns are identical, assign to 100% discount price
                p25_col = None
                explanation = f"В прайс-листе Биотек Фарм колонка '{p100_col}' назначена в 100% предоплату (колонка 25% не заполняется)."

            return ProposedFix(
                fix_id=fix_id,
                distributor_key=discrepancy.distributor_key,
                distributor_label=discrepancy.distributor_label,
                raw_filename=discrepancy.raw_filename,
                issue_summary=discrepancy.description,
                root_cause=root_cause,
                proposed_rule={
                    "name_col": name_col,
                    "p25_col": p25_col,
                    "p100_col": p100_col,
                },
                explanation=explanation
            )
    except Exception as ex:
        logger.error(f"Error calling Gemini for fix proposal: {ex}")

    # Return heuristic fix if Gemini call failed
    if discrepancy.issue_type == "product_missing":
        raw_p = sample_data.get("raw_product_name", "Препарат")
        target_p = sample_data.get("target_template_product", "Шаблон")
        root_cause = f"Препарат «{raw_p}» не распознан или пропущен алгоритмом сопоставления с позицией «{target_p}»."
        explanation = f"Добавлено синонимическое сопоставление для «{raw_p}» ➔ «{target_p}»."
    else:
        if discrepancy.distributor_key == "biotek":
            fallback_p25 = None
            fallback_p100 = numeric_cols[0] if numeric_cols else "Цена"
            root_cause = "В прайс-листе Биотек Фарм обнаружена только одна колонка цен без отдельных колонок скидок."
            explanation = f"Назначить для Биотек Фарм 100% со скидкой ➔ '{fallback_p100}', колонка 25% не заполняется."
        else:
            root_cause = "Обнаружено смещение или дублирование колонок цен у дистрибьютора."
            explanation = f"Автоматически сопоставлены колонки: Базовая 25% ➔ '{fallback_p25}', 100% со скидкой ➔ '{fallback_p100}'."

    return ProposedFix(
        fix_id=fix_id,
        distributor_key=discrepancy.distributor_key,
        distributor_label=discrepancy.distributor_label,
        raw_filename=discrepancy.raw_filename,
        issue_summary=discrepancy.description,
        root_cause=root_cause,
        proposed_rule={
            "name_col": fallback_name,
            "p25_col": fallback_p25,
            "p100_col": fallback_p100,
        },
        explanation=explanation
    )

