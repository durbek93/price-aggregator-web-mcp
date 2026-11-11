# -*- coding: utf-8 -*-
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import google.generativeai as genai

import config
from auditor import _read_excel_file, find_latest_svodny, audit_svodny_price, DISTRIBUTOR_MAP
from api_client import (
    get_distributor_rules,
    save_distributor_rule,
    trigger_rerun_pipeline,
    wait_for_task_completion,
    get_recent_tasks,
    get_backend_files,
)

logger = logging.getLogger("debugger_agent.dialog")

if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)


def get_available_raw_files() -> List[Dict[str, Any]]:
    """Returns list of active raw files in upload directory with metadata."""
    if not config.UPLOAD_DIR.exists():
        return []
    res = []
    for p in config.UPLOAD_DIR.glob("**/*.*"):
        if p.suffix.lower() in [".xlsx", ".xls"] and not p.name.startswith("~$") and "history" not in p.parts:
            try:
                stat = p.stat()
                mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
                res.append({
                    "filename": p.name,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "last_downloaded": mtime_str
                })
            except Exception:
                res.append({"filename": p.name})
    res.sort(key=lambda x: str(x.get("filename", "")).lower())
    return res


def get_files_status_summary(query: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns detailed status and metadata for all raw supplier files and their history."""
    if not config.UPLOAD_DIR.exists():
        return []
    
    q_low = query.lower().strip() if query else ""
    summary = []
    for p in config.UPLOAD_DIR.glob("**/*.*"):
        if p.suffix.lower() not in [".xlsx", ".xls"] or p.name.startswith("~$") or "history" in p.parts:
            continue
        if q_low and q_low not in p.name.lower():
            continue

        try:
            stat = p.stat()
            mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
            size_kb = round(stat.st_size / 1024, 1)

            # Check history folder for previous versions
            stem = p.stem
            history_matches = []
            for hp in config.UPLOAD_DIR.glob(f"**/history/{stem}_*.*"):
                if hp.is_file():
                    h_stat = hp.stat()
                    h_time = datetime.fromtimestamp(h_stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
                    history_matches.append({
                        "filename": hp.name,
                        "downloaded_at": h_time,
                        "size_kb": round(h_stat.st_size / 1024, 1)
                    })
            history_matches.sort(key=lambda x: x["downloaded_at"], reverse=True)

            summary.append({
                "filename": p.name,
                "last_downloaded": mtime_str,
                "size_kb": size_kb,
                "history_versions_count": len(history_matches),
                "recent_history": history_matches[:3]
            })
        except Exception as e:
            logger.warning(f"Error reading file status for {p}: {e}")

    summary.sort(key=lambda x: str(x.get("filename", "")).lower())
    return summary


def inspect_raw_file(filename: str, max_rows: int = 5) -> Dict[str, Any]:
    """Inspects raw Excel file and returns metadata, columns, and sample rows."""
    raw_files = list(config.UPLOAD_DIR.glob(f"**/{filename}"))
    if not raw_files:
        fn_low = filename.lower()
        candidates = [p for p in config.UPLOAD_DIR.glob("**/*.*") if fn_low in p.name.lower() and p.suffix.lower() in [".xlsx", ".xls"]]
        if candidates:
            raw_files = candidates
    if not raw_files:
        return {"error": f"Файл '{filename}' не найден в папке загрузок."}

    path = raw_files[0]
    try:
        stat = path.stat()
        last_downloaded = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
        file_size_kb = round(stat.st_size / 1024, 1)
    except Exception:
        last_downloaded = "не определена"
        file_size_kb = 0

    # History versions
    stem = path.stem
    history_matches = []
    for hp in config.UPLOAD_DIR.glob(f"**/history/{stem}_*.*"):
        if hp.is_file():
            try:
                h_stat = hp.stat()
                h_time = datetime.fromtimestamp(h_stat.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
                history_matches.append({
                    "filename": hp.name,
                    "downloaded_at": h_time,
                    "size_kb": round(h_stat.st_size / 1024, 1)
                })
            except Exception:
                pass
    history_matches.sort(key=lambda x: x["downloaded_at"], reverse=True)

    df = _read_excel_file(path)
    if df.empty:
        return {
            "filename": path.name,
            "last_downloaded": last_downloaded,
            "file_size_kb": file_size_kb,
            "history_count": len(history_matches),
            "recent_history": history_matches[:5],
            "error": f"Не удалось прочитать таблицу файла '{path.name}' (пустая таблица)."
        }

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
        "last_downloaded": last_downloaded,
        "file_size_kb": file_size_kb,
        "history_count": len(history_matches),
        "recent_history": history_matches[:5],
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


SYSTEM_PROMPT = """Ты — Главный Системный Аудитор и Отладчик экосистемы фармацевтического прайс-агрегатора (Price Aggregator MCP).
Ты работаешь в защищенном изолированном окружении проекта и обладаешь ПОЛНЫМИ И БЕЗГРАНИЧНЫМИ ПРАВАМИ АДМИНИСТРАТОРА внутри этого проекта:

1. ТЫ ОБЛАДАЕШЬ АБСОЛЮТНЫМ ДОСТУПОМ ко всем файлам дистрибьюторов в папке uploads, их метаданным, точным датам и времени скачивания/модификации, размерам, полной истории предыдущих скачиваний в папке history, колонкам, строкам, ценам, правилам сопоставления и фоновым задачам бэкенда.
2. ТЫ НИКОГДА НЕ ДОЛЖЕН говорить пользователю «у меня нет доступа к этим данным» или «мои функции ограничены». Все данные проекта тебе доступны через твои инструменты:
   - `inspect_distributor_file` — детальная инспекция файла: дата и время скачивания, размер, история выгрузок, колонки и строки с ценами;
   - `get_files_status` — сводка по файлам дистрибьюторов: точные даты скачивания, свежесть, размеры и количество архивных версий;
   - `get_system_tasks_status` — статус последних задач фонового сбора прайсов (Scout), генерации сводных матриц и ошибок;
   - `save_and_rebuild_svodny` — изменение правил сопоставления колонок и пересборка сводного прайса.
3. Если пользователь спрашивает, когда был скачан файл (например: «а когда был скачан этот прайс?», «откуда цены Фарма Чойза?»), откуда берутся цены, какие файлы загружены, статус фоновых задач сбора или сборки прайса — ВСЕГДА вызывай свои инструменты (`inspect_distributor_file`, `get_files_status`, `get_system_tasks_status`) и давай точный, развернутый и конкретный ответ с точной датой, временем и фактами.
4. Если пользователь просит настроить колонки или пересобрать прайс — выполняй действие через `save_and_rebuild_svodny`.
5. Отвечай профессионально, четко, структурированно, используя HTML-теги для Telegram (<b>жирный</b>, <code>код</code>, <i>курсив</i>).
6. Твоя зона ответственности и абсолютных полномочий — целиком и полностью данный проект агрегации цен.
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
- Доступные активные файлы дистрибьюторов в uploads (с датами скачивания): {json.dumps(raw_files, ensure_ascii=False)}
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
                    description="Открывает и инспектирует конкретный Excel-файл дистрибьютора из папки uploads (точная дата и время скачивания, размер файла, история предыдущих скачиваний, шапка, список колонок, числовые колонки цен, примеры первых строк).",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "filename": genai.protos.Schema(type=genai.protos.Type.STRING, description="Имя файла дистрибьютора (например 'Pharma Choice.xlsx', 'BIOTEK FARM.xls' или 'MEROS PHARM.xlsx')")
                        },
                        required=["filename"]
                    )
                ),
                genai.protos.FunctionDeclaration(
                    name="get_files_status",
                    description="Возвращает сводку по всем файлам прайс-листов дистрибьюторов в системе: имя файла, точные дата и время скачивания, размер в КБ, количество версий в истории.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "query": genai.protos.Schema(type=genai.protos.Type.STRING, description="Опциональное имя или часть имени дистрибьютора/файла для фильтрации (например 'pharma' или 'biotek')")
                        }
                    )
                ),
                genai.protos.FunctionDeclaration(
                    name="get_system_tasks_status",
                    description="Возвращает статус последних задач бэкенда (сбор прайсов скаутом, пересборка сводного прайса, их статус, результат, время запуска и завершения).",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "limit": genai.protos.Schema(type=genai.protos.Type.INTEGER, description="Количество последних задач (по умолчанию 5)")
                        }
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
                elif name == "get_files_status":
                    q = args.get("query")
                    data = get_files_status_summary(q)
                    tool_responses.append(genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=name,
                            response={"result": data}
                        )
                    ))
                elif name == "get_system_tasks_status":
                    lim = int(args.get("limit", 5))
                    data = await get_recent_tasks(lim)
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
