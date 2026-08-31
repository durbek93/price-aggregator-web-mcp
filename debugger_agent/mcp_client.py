# -*- coding: utf-8 -*-
import logging
import asyncio
from typing import Dict, Any, Optional

from mcp_servers.debugger_server import (
    get_distributor_rules as mcp_get_distributor_rules,
    save_distributor_rule as mcp_save_distributor_rule,
    audit_excel_file as mcp_audit_excel_file,
    trigger_pipeline_rerun as mcp_trigger_pipeline_rerun,
    check_pipeline_task_status as mcp_check_pipeline_task_status
)

logger = logging.getLogger("debugger_agent.mcp_client")


def fetch_rules() -> Dict[str, Any]:
    """Получает правила парсинга дистрибьюторов через MCP-сервер."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_get_distributor_rules())
    except Exception as e:
        logger.exception("Error calling mcp_get_distributor_rules")
        return {}


def update_rule(distributor_key: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    """Сохраняет правило парсинга через MCP-сервер."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_save_distributor_rule(distributor_key, rule))
    except Exception as e:
        logger.exception("Error calling mcp_save_distributor_rule")
        return {"status": "error", "error": str(e)}


def inspect_file(relative_path: str, max_rows: int = 5) -> Dict[str, Any]:
    """Инспектирует структуру Excel-файла прайса через MCP-сервер."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_audit_excel_file(relative_path, max_rows))
    except Exception as e:
        logger.exception("Error calling mcp_audit_excel_file")
        return {"error": str(e)}


def rerun_pipeline() -> Dict[str, Any]:
    """Запускает пересчет сводного отчета через MCP-сервер."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_trigger_pipeline_rerun())
    except Exception as e:
        logger.exception("Error calling mcp_trigger_pipeline_rerun")
        return {"status": "error", "error": str(e)}


def check_task(task_id: int) -> Dict[str, Any]:
    """Проверяет статус задачи через MCP-сервер."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_check_pipeline_task_status(task_id))
    except Exception as e:
        logger.exception("Error calling mcp_check_pipeline_task_status")
        return {"status": "error", "error": str(e)}


DEBUGGER_MCP_TOOLS = [
    fetch_rules,
    update_rule,
    inspect_file,
    rerun_pipeline,
    check_task
]
