# -*- coding: utf-8 -*-
import logging
import asyncio
from typing import Optional, Dict, Any

from mcp_servers.analytics_server import (
    fetch_price_comparison as mcp_fetch_price_comparison,
    fetch_manufacturer_trends as mcp_fetch_manufacturer_trends,
    fetch_drug_price_history as mcp_fetch_drug_price_history,
    fetch_system_summary as mcp_fetch_system_summary,
    fetch_sales_analysis as mcp_fetch_sales_analysis
)

logger = logging.getLogger("analyst_agent.mcp_client")


def get_price_comparison(date1: Optional[str] = None, date2: Optional[str] = None) -> Dict[str, Any]:
    """
    Получает сравнительный анализ цен и дельту между двумя датами или последний недельный отчет.
    date1: первая дата в формате DD.MM.YYYY
    date2: вторая дата в формате DD.MM.YYYY
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_fetch_price_comparison(date1, date2))
    except Exception as e:
        logger.exception("Error calling mcp_fetch_price_comparison")
        return {"error": str(e)}


def get_manufacturer_trends(producer: str, days: int = 30) -> Dict[str, Any]:
    """
    Получает динамику цен и тренды для конкретного производителя за указанное количество дней.
    producer: название производителя (например 'Материа Медика')
    days: количество дней ретроспективы (по умолчанию 30)
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_fetch_manufacturer_trends(producer, days))
    except Exception as e:
        logger.exception("Error calling mcp_fetch_manufacturer_trends")
        return {"error": str(e)}


def get_drug_price_history(drug: str, days: int = 30) -> Dict[str, Any]:
    """
    Получает историю изменения цен на конкретный лекарственный препарат.
    drug: название препарата (например 'Анаферон Детский', 'Ренгалин')
    days: количество дней (по умолчанию 30)
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_fetch_drug_price_history(drug, days))
    except Exception as e:
        logger.exception("Error calling mcp_fetch_drug_price_history")
        return {"error": str(e)}


def get_system_summary() -> Dict[str, Any]:
    """
    Получает общую сводку состояния системы (список прайсов, даты сводных отчетов, размер базы).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_fetch_system_summary())
    except Exception as e:
        logger.exception("Error calling mcp_fetch_system_summary")
        return {"error": str(e)}


def get_sales_analysis() -> Dict[str, Any]:
    """
    Получает аналитику и сводные данные по отчетам о продажах.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(mcp_fetch_sales_analysis())
    except Exception as e:
        logger.exception("Error calling mcp_fetch_sales_analysis")
        return {"error": str(e)}


ANALYST_MCP_TOOLS = [
    get_price_comparison,
    get_manufacturer_trends,
    get_drug_price_history,
    get_system_summary,
    get_sales_analysis
]
