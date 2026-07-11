# -*- coding: utf-8 -*-
import os
import logging
from typing import List, Optional
import httpx

import config

logger = logging.getLogger("scout_agent.api_client")


async def upload_file_to_backend(file_path: str) -> Optional[int]:
    """Загружает файл на бэкенд FastAPI с использованием X-Internal-API-Key."""
    try:
        filename = os.path.basename(file_path)
        logger.info(f"Uploading file {filename} to backend...")
        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                files = {
                    "file": (
                        filename,
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                }
                headers = {
                    "X-Internal-API-Key": config.INTERNAL_API_KEY,
                    "X-Target-User-ID": "1"
                }
                response = await client.post(
                    f"{config.BACKEND_URL}/api/files/upload",
                    files=files,
                    headers=headers,
                    timeout=60.0
                )
            
            if response.status_code == 200:
                data = response.json()
                file_id = data.get("id")
                logger.info(f"Successfully uploaded file {filename} -> DB ID: {file_id}")
                return file_id
            else:
                logger.error(
                    f"Failed to upload file {filename}. Code: {response.status_code}, Detail: {response.text}"
                )
                return None
    except Exception as e:
        logger.exception(f"Exception during file upload: {e}")
        return None


async def trigger_aggregation_task(file_ids: List[int]) -> bool:
    """Запускает Celery задачу сборки на бэкенде."""
    try:
        logger.info(f"Triggering horizontal aggregation task for file IDs: {file_ids}")
        async with httpx.AsyncClient() as client:
            headers = {
                "X-Internal-API-Key": config.INTERNAL_API_KEY,
                "X-Target-User-ID": "1",
                "Content-Type": "application/json"
            }
            body = {
                "task_type": "svodny_horizontal",
                "is_automated": True,
                "file_ids": file_ids
            }
            response = await client.post(
                f"{config.BACKEND_URL}/api/tasks",
                json=body,
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Aggregation task successfully queued. Task record ID: {data.get('id')}")
                return True
            else:
                logger.error(f"Failed to trigger task. Code: {response.status_code}, Detail: {response.text}")
                return False
    except Exception as e:
        logger.exception(f"Exception during task trigger: {e}")
        return False
