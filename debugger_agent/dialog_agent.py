# -*- coding: utf-8 -*-
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import google.generativeai as genai

import config
from auditor import _read_excel_file, find_latest_svodny, audit_svodny_price, DISTRIBUTOR_MAP
from api_client import get_distributor_rules, save_distributor_rule, trigger_rerun_pipeline, wait_for_task_completion

logger = logging.getLogger("debugger_agent.dialog")

if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)


def get_available_raw_files() -> List[str]:
    """Returns list of relative file names in upload directory."""
    if not config.UPLOAD_DIR.exists():
        return []
    res = []
    for p in config.UPLOAD_DIR.glob("**/*.*"):
        if p.suffix.lower() in [".xlsx", ".xls"] and not p.name.startswith("~$") and "history" not in p.parts:
            res.append(p.name)
    return sorted(list(set(res)))


def inspect_raw_file(filename: str, max_rows: int = 5) -> Dict[str, Any]:
    """Inspects raw Excel file and returns columns and sample rows."""
    raw_files = list(config.UPLOAD_DIR.glob(f"**/{filename}"))
    if not raw_files:
        # Search by substring
        fn_low = filename.lower()
        candidates = [p for p in config.UPLOAD_DIR.glob("**/*.*") if fn_low in p.name.lower() and p.suffix.lower() in [".xlsx", ".xls"]]
        if candidates:
            raw_files = candidates
    if not raw_files:
        return {"error": f"Файл '{filename}' не найден в папке загрузок."}

    path = raw_files[0]
    df = _read_excel_file(path)
    if df.empty:
        return {"error": f"Не удалось прочитать файл '{path.name}' (пустая таблица)."}

    cols = list(df.columns)
    sample_rows = []
    for i in range(min(max_rows, len(df))):
        sample_rows.append({str(k): (None if str(v).lower() == "nan" else str(v)) for k, v in df.iloc[i].to_dict().items()})

    numeric_cols = []
    for c in cols:
        valid_cnt = 0
        for v in df[c].dropna().head(100):
            try:
                if float(v) > 500:
                    valid_cnt += 1
            except (ValueError, TypeError):
                pass
        if valid_cnt >= 3:
            numeric_cols.append(str(c))

    return {
        "filename": path.name,
        "total_rows": len(df),
        "columns": cols,
        "numeric_price_columns": numeric_cols,
        "sample_rows": sample_rows
    }


async def execute_save_and_rebuild(distributor_key: str, name_col: str, p25_col: Optional[str], p100_col: Optional[str]) -> Dict[str, Any]:
    """Saves custom distributor rule, triggers pipeline rerun, and re-audits."""
    rule = {
        "name_col": name_col,
        "p25_col": p25_col,
        "p100_col": p100_col
    }
    saved = save_distributor_rule(distributor_key, rule)
    if not saved:
        return {"status": "error", "message": f"Не удалось сохранить правило для {distributor_key} в distributor_rules.json"}

    task_id = await trigger_rerun_pipeline()
    if not task_id:
        return {"status": "error", "message": "Ошибка запуска задачи пересборки в бэкенде."}

    success = await wait_for_task_completion(task_id, timeout_sec=180)
    if not success:
        return {"status": "error", "message": f"Пересборка прайса (task {task_id}) завершилась сбоем или таймаутом."}

    latest = find_latest_svodny(config.OUTPUT_DIR)
    new_report_summary = "Сводный прайс обновлен."
    if latest:
        report = audit_svodny_price(latest, config.UPLOAD_DIR)
        new_report_summary = report.summary_text

    return {
        "status": "success",
        "message": f"Правило для {distributor_key} успешно применено. Сводный прайс пересобран.",
        "audit_summary": new_report_summary
    }


SYSTEM_PROMPT = """Ты — интеллектуальный Агент-Аудитор и Отладчик системы сводного фармацевтического прайса.
Ты общаешься с администраторами и аналитиками в Telegram. Твоя задача:
1. Понятно и дружелюбно объяснять, что происходит с прайс-листами дистрибьюторов (Гранд Фарм, Мерос, Биотек Фарм, Фарм Люкс, Зента, Аэро и др.) и препаратами «Материа Медика».
2. Если пользователь просит тебя проверить файл или объяснить, почему в своднике что-то не заполнено — заглядывай в структуру файлов и аргументированно отвечай.
3. Если пользователь даёт прямое указание настроить колонку (например: "возьми колонку 'Цена' как 100% со скидкой и пересобери") — выполни это действие через инструмент save_and_rebuild.
4. Отвечай кратко, чётко, структурированно, профессионально, используя HTML-теги для Telegram (<b>жирный</b>, <code>код</code>, <i>курсив</i>).
"""


async def answer_user_query(
    user_message: str,
    replied_message_text: Optional[str] = None
) -> str:
    """Answers user message with tool calling capabilities using Gemini."""
    if not config.GEMINI_API_KEY:
        return "⚠️ Модуль ИИ-рассуждений не настроен (отсутствует GEMINI_API_KEY)."

    # Gather initial environment context
    rules = get_distributor_rules()
    latest_sv = find_latest_svodny(config.OUTPUT_DIR)
    raw_files = get_available_raw_files()

    context_str = f"""
Текущий контекст системы:
- Последний сводный прайс: {latest_sv.name if latest_sv else 'не найден'}
- Сохраненные правила дистрибьюторов: {json.dumps(rules, ensure_ascii=False)}
- Доступные файлы дистрибьюторов в uploads: {raw_files}
- Известные ключи дистрибьюторов: {list(DISTRIBUTOR_MAP.keys())}
"""
    if replied_message_text:
        context_str += f"\nПользователь ответил (Reply) на предыдущее сообщение бота:\n«««\n{replied_message_text}\n»»»\n"

    # Define tools for Gemini
    tools = [
        genai.protos.Tool(
            function_declarations=[
                genai.protos.FunctionDeclaration(
                    name="inspect_distributor_file",
                    description="Открывает и инспектирует структуру реального Excel-файла дистрибьютора из папки uploads (шапка, список колонок, числовые колонки цен, примеры первых строк).",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "filename": genai.protos.Schema(type=genai.protos.Type.STRING, description="Имя файла дистрибьютора (например 'BIOTEK FARM.xls' или 'MEROS PHARM.xlsx')")
                        },
                        required=["filename"]
                    )
                ),
                genai.protos.FunctionDeclaration(
                    name="save_and_rebuild_svodny",
                    description="Сохраняет правило сопоставления колонок для дистрибьютора, пересобирает сводный прайс и проверяет результат новым аудитом.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "distributor_key": genai.protos.Schema(type=genai.protos.Type.STRING, description="Ключ дистрибьютора (например 'biotek', 'meros', 'grand', 'luxe', 'zenta')"),
                            "name_col": genai.protos.Schema(type=genai.protos.Type.STRING, description="Название колонки с наименованием препарата"),
                            "p25_col": genai.protos.Schema(type=genai.protos.Type.STRING, description="Название колонки базовой цены (25%), либо пустая строка / null если нет"),
                            "p100_col": genai.protos.Schema(type=genai.protos.Type.STRING, description="Название колонки скидочной цены (100%), либо пустая строка / null")
                        },
                        required=["distributor_key", "name_col"]
                    )
                ),
            ]
        )
    ]

    model = genai.GenerativeModel(
        model_name=config.GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        tools=tools
    )

    chat = model.start_chat(enable_automatic_function_calling=False)
    prompt = f"{context_str}\nСообщение пользователя: {user_message}"

    try:
        response = await chat.send_message_async(prompt)
        
        # Multi-turn tool execution loop
        max_iterations = 4
        while max_iterations > 0:
            max_iterations -= 1
            function_calls = []
            for part in response.parts:
                if part.function_call:
                    function_calls.append(part.function_call)

            if not function_calls:
                # No more tools called, return final text
                return response.text or "✅ Сообщение обработано."

            # Execute tool calls
            tool_responses = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args)
                logger.info(f"Agent called tool '{name}' with args {args}")

                if name == "inspect_distributor_file":
                    fn = args.get("filename", "")
                    data = inspect_raw_file(fn)
                    tool_responses.append(genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=name,
                            response={"result": data}
                        )
                    ))
                elif name == "save_and_rebuild_svodny":
                    dk = args.get("distributor_key", "")
                    nc = args.get("name_col", "Наименование")
                    p25 = args.get("p25_col")
                    if p25 in ["", "null", "None"]:
                        p25 = None
                    p100 = args.get("p100_col")
                    if p100 in ["", "null", "None"]:
                        p100 = None

                    res = await execute_save_and_rebuild(dk, nc, p25, p100)
                    tool_responses.append(genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=name,
                            response={"result": res}
                        )
                    ))

            response = await chat.send_message_async(tool_responses)

        return response.text or "✅ Запрос выполнен."

    except Exception as e:
        logger.exception(f"Error in conversational agent: {e}")
        return f"⚠️ Произошла ошибка при обработке запроса: <code>{html_escape(str(e))}</code>"


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
