# -*- coding: utf-8 -*-
import logging
from typing import Optional
import httpx

import config

logger = logging.getLogger("analyst_agent.backend_client")


async def fetch_analysis_data(date1: Optional[str] = None, date2: Optional[str] = None) -> Optional[dict]:
    """Запрашивает дельту цен с бэкенда FastAPI для общего еженедельного анализа или сравнения двух конкретных дат."""
    try:
        logger.info(f"Fetching price comparison analysis from backend (date1={date1}, date2={date2})...")
        headers = {
            "X-Internal-API-Key": config.INTERNAL_API_KEY,
            "X-Target-User-ID": "1"
        }
        params = {}
        if date1:
            params["date1"] = date1
        if date2:
            params["date2"] = date2

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.BACKEND_URL}/api/analysis/compare",
                params=params,
                headers=headers,
                timeout=60.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to fetch comparison. Code: {response.status_code}, Detail: {response.text}"
                )
                return None
    except Exception as e:
        logger.exception(f"Exception during fetching analysis data: {e}")
        return None


async def fetch_manufacturer_data(producer: str, days: int) -> Optional[dict]:
    """Запрашивает исторические данные по производителю с бэкенда."""
    try:
        logger.info(f"Fetching manufacturer raw price history from backend for {producer} (days={days})...")
        headers = {
            "X-Internal-API-Key": config.INTERNAL_API_KEY,
            "X-Target-User-ID": "1"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.BACKEND_URL}/api/analysis/manufacturer-compare",
                params={"producer": producer, "days": days},
                headers=headers,
                timeout=60.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to fetch manufacturer compare. Code: {response.status_code}, Detail: {response.text}"
                )
                return None
    except Exception as e:
        logger.exception(f"Exception during fetching manufacturer data: {e}")
        return None


async def fetch_drug_data(drug: str, days: int) -> Optional[dict]:
    """Запрашивает исторические данные по конкретному препарату с бэкенда."""
    try:
        logger.info(f"Fetching drug raw price history from backend for {drug} (days={days})...")
        headers = {
            "X-Internal-API-Key": config.INTERNAL_API_KEY,
            "X-Target-User-ID": "1"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.BACKEND_URL}/api/analysis/drug-compare",
                params={"drug": drug, "days": days},
                headers=headers,
                timeout=60.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to fetch drug compare. Code: {response.status_code}, Detail: {response.text}"
                )
                return None
    except Exception as e:
        logger.exception(f"Exception during fetching drug data: {e}")
        return None


async def fetch_system_summary() -> Optional[dict]:
    """Запрашивает сводку системы (файлы, сводные отчёты, каталог) с бэкенда."""
    try:
        logger.info("Fetching system summary from backend...")
        headers = {
            "X-Internal-API-Key": config.INTERNAL_API_KEY,
            "X-Target-User-ID": "1"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.BACKEND_URL}/api/analysis/system-summary",
                headers=headers,
                timeout=60.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to fetch system summary. Code: {response.status_code}, Detail: {response.text}"
                )
                return None
    except Exception as e:
        logger.exception(f"Exception during fetching system summary: {e}")
        return None


async def fetch_sales_data() -> Optional[dict]:
    """Запрашивает с бэкенда данные отчетов о продажах (из outputs/1/sales)."""
    try:
        logger.info("Fetching sales analysis from backend...")
        headers = {
            "X-Internal-API-Key": config.INTERNAL_API_KEY,
            "X-Target-User-ID": "1"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.BACKEND_URL}/api/analysis/sales-compare",
                headers=headers,
                timeout=60.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(
                    f"Failed to fetch sales compare. Code: {response.status_code}, Detail: {response.text}"
                )
                return None
    except Exception as e:
        logger.exception(f"Exception during fetching sales data: {e}")
        return None


