# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx
import pandas as pd
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_debugger_server")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
RULES_FILE = Path(os.getenv("RULES_FILE", "/app/data/distributor_rules.json"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/data/uploads"))

mcp = FastMCP("Price Aggregator Debugger MCP Server")


def _get_headers() -> dict:
    return {
        "X-Internal-API-Key": INTERNAL_API_KEY,
        "X-Target-User-ID": "1"
    }


@mcp.tool()
async def get_distributor_rules() -> Dict[str, Any]:
    """
    Возвращает текущие настроенные правила сопоставления колонок и листов дистрибьюторов из JSON-конфигурации.
    """
    try:
        if not RULES_FILE.exists():
            return {}
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.exception("Error reading distributor rules")
        return {"error": str(e)}


@mcp.tool()
async def save_distributor_rule(distributor_key: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    """
    Сохраняет или обновляет кастомное правило парсинга для конкретного дистрибьютора.
    Параметры rule:
    - sheet_name: название листа (или None)
    - header_row: номер строки с заголовками (0-indexed)
    - drug_col: название или индекс колонки с препаратом
    - producer_col: колонка с производителем
    - price_col: колонка с ценой
    - expiry_col: колонка со сроком годности (опционально)
    - quantity_col: колонка с остатком/количеством (опционально)
    """
    try:
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        current = {}
        if RULES_FILE.exists():
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                current = json.load(f)
        current[distributor_key] = rule
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved distributor rule for '{distributor_key}': {rule}")
        return {"status": "success", "distributor_key": distributor_key, "rule": rule}
    except Exception as e:
        logger.exception("Error saving distributor rule")
        return {"status": "error", "error": str(e)}


@mcp.tool()
async def audit_excel_file(relative_path: str, max_rows: int = 5) -> Dict[str, Any]:
    """
    Анализирует структуру загруженного Excel-файла прайса: читает список листов, определяет заголовки и возвращает первые строки.
    relative_path: путь относительно папки uploads (например '1/AERO.xlsx')
    """
    try:
        file_path = UPLOAD_DIR / relative_path
        if not file_path.exists():
            # Попробуем прямой путь если передан полный
            file_path = Path(relative_path)
            if not file_path.exists():
                return {"error": f"File not found: {relative_path}"}

        excel_file = pd.ExcelFile(file_path)
        sheets_info = {}
        for sheet_name in excel_file.sheet_names[:5]:  # Ограничиваем первыми 5 листами
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=max_rows, header=None)
                sample_data = df.fillna("").values.tolist()
                sheets_info[sheet_name] = {
                    "total_rows_preview": len(sample_data),
                    "sample_rows": sample_data
                }
            except Exception as se:
                sheets_info[sheet_name] = {"error": str(se)}

        return {
            "file_name": file_path.name,
            "sheet_names": excel_file.sheet_names,
            "sheets_preview": sheets_info
        }
    except Exception as e:
        logger.exception("Error auditing Excel file")
        return {"error": str(e)}


@mcp.tool()
async def trigger_pipeline_rerun() -> Dict[str, Any]:
    """
    Инициирует фоновый пересчет сводного горизонтального прайса через backend API.
    """
    try:
        headers = _get_headers()
        headers["Content-Type"] = "application/json"
        payload = {
            "task_type": "svodny_horizontal",
            "is_automated": True
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{BACKEND_URL}/api/tasks",
                json=payload,
                headers=headers
            )
            if resp.status_code in [200, 201]:
                data = resp.json()
                return {"status": "success", "task_id": data.get("id")}
            return {"status": "error", "code": resp.status_code, "detail": resp.text}
    except Exception as e:
        logger.exception("Error triggering pipeline rerun")
        return {"status": "error", "error": str(e)}


@mcp.tool()
async def check_pipeline_task_status(task_id: int) -> Dict[str, Any]:
    """
    Проверяет текущий статус выполнения задачи по task_id в бэкенде.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/tasks",
                headers=_get_headers()
            )
            if resp.status_code == 200:
                tasks = resp.json()
                for t in tasks:
                    if t.get("id") == task_id:
                        return {
                            "task_id": task_id,
                            "status": t.get("status"),
                            "progress": t.get("progress"),
                            "message": t.get("progress_message")
                        }
                return {"task_id": task_id, "status": "not_found"}
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
    except Exception as e:
        logger.exception("Error checking pipeline task status")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
