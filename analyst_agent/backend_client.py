# -*- coding: utf-8 -*-
import logging
from typing import Optional
import httpx

import config

logger = logging.getLogger("analyst_agent.backend_client")


async def fetch_analysis_data() -> Optional[dict]:
    """Запрашивает дельту цен с бэкенда FastAPI для общего еженедельного анализа."""
    try:
        logger.info("Fetching price comparison analysis from backend...")
        headers = {
            "X-Internal-API-Key": config.INTERNAL_API_KEY,
            "X-Target-User-ID": "1"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.BACKEND_URL}/api/analysis/compare",
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
