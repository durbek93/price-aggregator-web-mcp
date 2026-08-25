# -*- coding: utf-8 -*-
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

import config

logger = logging.getLogger("debugger_agent.api_client")


def get_distributor_rules() -> Dict[str, Any]:
    """Reads saved distributor rules from JSON file."""
    if not config.RULES_FILE.exists():
        return {}
    try:
        with open(config.RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading {config.RULES_FILE}: {e}")
        return {}


def save_distributor_rule(distributor_key: str, rule: Dict[str, Any]) -> bool:
    """Saves or updates custom distributor parsing rule."""
    try:
        config.RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        current = get_distributor_rules()
        current[distributor_key] = rule
        with open(config.RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved distributor rule for '{distributor_key}': {rule}")
        return True
    except Exception as e:
        logger.error(f"Failed to save distributor rule: {e}")
        return False


async def trigger_rerun_pipeline() -> Optional[int]:
    """Triggers svodny_horizontal task via backend internal API."""
    headers = {
        "X-Internal-API-Key": config.INTERNAL_API_KEY,
        "X-Target-User-ID": "1",
        "Content-Type": "application/json"
    }
    payload = {
        "task_type": "svodny_horizontal",
        "is_automated": True
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{config.BACKEND_URL}/api/tasks",
                json=payload,
                headers=headers
            )
            if resp.status_code in [200, 201]:
                data = resp.json()
                task_id = data.get("id")
                logger.info(f"Triggered re-run task ID: {task_id}")
                return task_id
            else:
                logger.error(f"Failed to trigger task: HTTP {resp.status_code} - {resp.text}")
    except Exception as ex:
        logger.error(f"Exception triggering re-run task: {ex}")
    return None


async def wait_for_task_completion(task_id: int, timeout_sec: int = 90) -> bool:
    """Polls backend until task is completed or failed."""
    headers = {
        "X-Internal-API-Key": config.INTERNAL_API_KEY,
        "X-Target-User-ID": "1"
    }
    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) < timeout_sec:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{config.BACKEND_URL}/api/tasks",
                    headers=headers
                )
                if resp.status_code == 200:
                    tasks = resp.json()
                    for t in tasks:
                        if t.get("id") == task_id:
                            status = t.get("status")
                            if status == "completed":
                                return True
                            elif status == "failed":
                                logger.error(f"Task {task_id} failed: {t.get('progress_message')}")
                                return False
        except Exception as e:
            logger.warning(f"Error checking task status: {e}")
        await asyncio.sleep(2)
    return False
