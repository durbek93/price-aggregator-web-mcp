# -*- coding: utf-8 -*-
import os
import sys
import logging
from typing import Optional, Dict, Any
import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_analytics_server")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

mcp = FastMCP("Price Aggregator Analytics MCP Server")


def _get_headers() -> dict:
    return {
        "X-Internal-API-Key": INTERNAL_API_KEY,
        "X-Target-User-ID": "1"
    }


@mcp.tool()
async def fetch_price_comparison(date1: Optional[str] = None, date2: Optional[str] = None) -> Dict[str, Any]:
    """
    Запрашивает дельту и сравнение цен с бэкенда для общего еженедельного анализа или сравнения двух конкретных дат (формат DD.MM.YYYY).
    """
    try:
        logger.info(f"MCP: fetch_price_comparison(date1={date1}, date2={date2})")
        params = {}
        if date1:
            params["date1"] = date1
        if date2:
            params["date2"] = date2

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/analysis/compare",
                params=params,
                headers=_get_headers()
            )
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
    except Exception as e:
        logger.exception("Error in fetch_price_comparison")
        return {"error": str(e)}


@mcp.tool()
async def fetch_manufacturer_trends(producer: str, days: int = 30) -> Dict[str, Any]:
    """
    Запрашивает исторические данные изменения цен по конкретному производителю за указанное количество дней.
    """
    try:
        logger.info(f"MCP: fetch_manufacturer_trends(producer='{producer}', days={days})")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/analysis/manufacturer-compare",
                params={"producer": producer, "days": days},
                headers=_get_headers()
            )
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
    except Exception as e:
        logger.exception("Error in fetch_manufacturer_trends")
        return {"error": str(e)}


@mcp.tool()
async def fetch_drug_price_history(drug: str, days: int = 30) -> Dict[str, Any]:
    """
    Запрашивает исторические данные по ценам конкретного препарата/медикамента с бэкенда.
    """
    try:
        logger.info(f"MCP: fetch_drug_price_history(drug='{drug}', days={days})")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/analysis/drug-compare",
                params={"drug": drug, "days": days},
                headers=_get_headers()
            )
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
    except Exception as e:
        logger.exception("Error in fetch_drug_price_history")
        return {"error": str(e)}


@mcp.tool()
async def fetch_system_summary() -> Dict[str, Any]:
    """
    Запрашивает общую сводку системы (загруженные прайсы, даты сводных отчетов, размер каталога).
    """
    try:
        logger.info("MCP: fetch_system_summary()")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/analysis/system-summary",
                headers=_get_headers()
            )
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
    except Exception as e:
        logger.exception("Error in fetch_system_summary")
        return {"error": str(e)}


@mcp.tool()
async def fetch_sales_analysis() -> Dict[str, Any]:
    """
    Запрашивает с бэкенда анализ динамики отчетов о продажах компании.
    """
    try:
        logger.info("MCP: fetch_sales_analysis()")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/analysis/sales-compare",
                headers=_get_headers()
            )
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
    except Exception as e:
        logger.exception("Error in fetch_sales_analysis")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
