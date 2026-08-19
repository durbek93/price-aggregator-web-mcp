# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.worker import celery_app
from app.database import SessionLocal
from app.models import User, UserSettings, CatalogItem, FileRecord, TaskRecord
from app.config import settings
from app.defaults import DEFAULT_COLUMNS, DEFAULT_PRODUCERS

# Prepend core to sys.path so we can import modules correctly
core_dir = str(Path(__file__).parent.joinpath("core").absolute())
if core_dir not in sys.path:
    sys.path.insert(0, core_dir)

from app.core import pipeline
from aiogram import Bot
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)


def send_telegram_doc_sync(telegram_id: int, file_path: str, caption: str) -> None:
    """Вспомогательная функция для синхронной отправки документа в Telegram."""
    async def _send():
        try:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            doc = FSInputFile(file_path)
            await bot.send_document(chat_id=telegram_id, document=doc, caption=caption)
            await bot.session.close()
            logger.info(f"Report sent successfully to Telegram ID {telegram_id}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {telegram_id}: {e}")

    try:
        # Пытаемся получить текущий Event Loop или запустить новый
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Если loop уже запущен (в некоторых средах), запускаем таску в фоне
            loop.create_task(_send())
        else:
            loop.run_until_complete(_send())
    except RuntimeError:
        asyncio.run(_send())


@celery_app.task(bind=True, time_limit=300, soft_time_limit=240)
def run_pipeline_task(self, task_record_id: int) -> Dict[str, Any]:
    """Фоновая задача Celery для запуска обработки прайс-листов."""
    db = SessionLocal()
    task_record = db.query(TaskRecord).filter(TaskRecord.id == task_record_id).first()
    
    if not task_record:
        db.close()
        return {"status": "failed", "error": f"TaskRecord with ID {task_record_id} not found."}

    user = db.query(User).filter(User.id == task_record.user_id).first()
    if not user:
        task_record.status = "failed"
        task_record.progress_message = "Пользователь не найден."
        db.commit()
        db.close()
        return {"status": "failed", "error": "User not found."}

    # Обновляем статус задачи в БД
    task_record.status = "running"
    task_record.celery_task_id = self.request.id
    task_record.progress_message = "Инициализация параметров..."
    db.commit()
    
    start_time = time.time()

    try:
        # Загружаем настройки пользователя
        user_settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
        if not user_settings:
            # Создаем настройки по умолчанию, если их нет
            user_settings = UserSettings(
                user_id=user.id,
                columns=DEFAULT_COLUMNS,
                producers=DEFAULT_PRODUCERS,
                use_catalog_matching=False,
                legacy_priority_rules=False,
                clear_inputs_after_processing=True
            )
            db.add(user_settings)
            db.commit()
            db.refresh(user_settings)
        else:
            # Самовосстановление (self-healing): добавляем новые стандартные кандидаты, если их нет
            modified = False
            user_cols = dict(user_settings.columns or {})
            for k, default_list in DEFAULT_COLUMNS.items():
                current_list = list(user_cols.get(k, []))
                added = False
                for cand in default_list:
                    if cand not in current_list:
                        current_list.append(cand)
                        added = True
                if added:
                    user_cols[k] = current_list
                    modified = True
            if modified:
                user_settings.columns = user_cols
                db.commit()
                db.refresh(user_settings)


        settings_dict = {
            "columns": user_settings.columns,
            "producers": user_settings.producers,
            "use_catalog_matching": user_settings.use_catalog_matching,
            "legacy_priority_rules": user_settings.legacy_priority_rules,
        }

        # Загружаем каталог синонимов
        catalog_items = db.query(CatalogItem).filter(CatalogItem.user_id == user.id).all()
        catalog_list = []
        for item in catalog_items:
            catalog_list.append((item.canonical, item.aliases))

        # Загружаем список загруженных прайсов (input файлов)
        if task_record.file_ids:
            input_files_db = db.query(FileRecord).filter(
                FileRecord.user_id == user.id,
                FileRecord.file_type == "input",
                FileRecord.id.in_(task_record.file_ids)
            ).all()
        else:
            input_files_db = db.query(FileRecord).filter(
                FileRecord.user_id == user.id,
                FileRecord.file_type == "input"
            ).all()

        price_files = []
        for f in input_files_db:
            price_files.append({
                "filename": f.filename,
                "display_name": f.display_name,
                "read_preset": f.read_preset,
            })

        # Папки для пользователя
        user_upload_dir = settings.UPLOAD_DIR / str(user.id)
        user_output_dir = settings.OUTPUT_DIR / str(user.id)
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        user_output_dir.mkdir(parents=True, exist_ok=True)

        # Callback для обновления прогресса в БД
        def update_progress(msg: str) -> None:
            # Заново запрашиваем запись, чтобы избежать race conditions
            task_ref = db.query(TaskRecord).filter(TaskRecord.id == task_record_id).first()
            if task_ref:
                current = task_ref.progress_message or ""
                parts = [p.strip() for p in current.split("|||") if p.strip()]
                if msg not in parts:
                    parts.append(msg)
                # Ограничиваем длину строки в пределах 500 символов для типа String(512)
                while parts and len(" ||| ".join(parts)) > 500:
                    parts.pop(0)
                task_ref.progress_message = " ||| ".join(parts)
                db.commit()
            logger.info(f"Task {task_record_id} progress: {msg}")

        # Запуск соответствующего алгоритма конвейера
        task_type = task_record.task_type
        out_path = None
        result_msg = ""

        if task_type == "svodny_horizontal":
            out_path = pipeline.run_svodny_horizontal(
                settings_dict=settings_dict,
                catalog_list=catalog_list,
                price_files=price_files,
                upload_dir=user_upload_dir,
                output_dir=user_output_dir,
                progress=update_progress
            )
            result_msg = "Сводный прайс успешно собран."
        
        elif task_type == "svodny_vertical":
            out_path = pipeline.run_svodny_vertical(
                settings_dict=settings_dict,
                catalog_list=catalog_list,
                price_files=price_files,
                upload_dir=user_upload_dir,
                output_dir=user_output_dir,
                progress=update_progress
            )
            result_msg = "Сводный прайс (вертикально) успешно собран."

        elif task_type == "assortment":
            out_path = pipeline.run_assortment(
                settings_dict=settings_dict,
                price_files=price_files,
                upload_dir=user_upload_dir,
                output_dir=user_output_dir,
                progress=update_progress
            )
            result_msg = "Анализ ассортимента завершен."

        elif task_type == "cheapest":
            # Подсветка минимальных цен в выходной папке
            result_msg = pipeline.run_cheapest(output_dir=user_output_dir)
            # В данном случае итогового нового файла нет, изменяется существующий
            # Возьмем последний измененный XLSX файл в выходной папке как результат
            xlsx_files = sorted(user_output_dir.glob("*.xlsx"), key=os.path.getmtime)
            if xlsx_files:
                out_path = xlsx_files[-1]

        elif task_type == "best_suppliers":
            out_path = pipeline.run_best_suppliers_analysis(
                output_dir=user_output_dir,
                progress=update_progress
            )
            result_msg = "Анализ лучших поставщиков завершен."
        
        else:
            raise ValueError(f"Неизвестный тип задачи: {task_type}")

        duration_seconds = int(time.time() - start_time)
        result_msg = f"{result_msg} (Время выполнения: {duration_seconds} сек)"

        # Сохраняем информацию о выходном файле в БД
        if out_path and out_path.exists():
            file_size = out_path.stat().st_size
            
            # Создаем FileRecord для выходного файла
            file_record = FileRecord(
                user_id=user.id,
                filename=out_path.name,
                display_name=out_path.name,
                file_type="output",
                file_size=file_size,
                storage_path=str(out_path)
            )
            db.add(file_record)
            db.commit()

            # Обновляем запись задачи
            task_record.status = "completed"
            task_record.progress_message = result_msg
            task_record.result_file_path = str(out_path)
            db.commit()

            # Автоматическая очистка исходных прайсов после выполнения задачи
            if task_type in ["svodny_horizontal", "svodny_vertical", "assortment"] and getattr(user_settings, "clear_inputs_after_processing", True):
                try:
                    if task_record.file_ids:
                        input_files = db.query(FileRecord).filter(
                            FileRecord.user_id == user.id,
                            FileRecord.file_type == "input",
                            FileRecord.id.in_(task_record.file_ids)
                        ).all()
                    else:
                        input_files = db.query(FileRecord).filter(
                            FileRecord.user_id == user.id,
                            FileRecord.file_type == "input"
                        ).all()
                    for f in input_files:
                        # if os.path.exists(f.storage_path):
                        #     os.remove(f.storage_path)
                        # db.delete(f)
                        pass
                    # db.commit()
                    logger.info(f"Automatically cleared input files for user {user.id} after task {task_type}")
                except Exception as ex:
                    logger.error(f"Failed to automatically clear input files: {ex}")

            # Отправляем файл пользователю или в группу Telegram
            if task_record.is_automated and settings.TELEGRAM_GROUP_ID:
                caption = (
                    "📊 **Сводный прайс-лист собран автоматически!**\n\n"
                    "@lightprice_analyst_bot, подготовь аналитический отчет по изменениям цен."
                )
                group_id_val = settings.TELEGRAM_GROUP_ID
                if group_id_val.startswith("-") and group_id_val[1:].isdigit():
                    group_id_val = int(group_id_val)
                elif group_id_val.isdigit():
                    group_id_val = int(group_id_val)
                send_telegram_doc_sync(group_id_val, str(out_path), caption)
            else:
                caption = f"✅ Задача {task_type} успешно выполнена!\n📄 Результат: {out_path.name}"
                send_telegram_doc_sync(user.telegram_id, str(out_path), caption)

            # Notify Debugger Agent to verify output
            if task_type in ["svodny_horizontal", "svodny_vertical"]:
                try:
                    import urllib.request
                    req = urllib.request.Request(
                        "http://debugger_agent:8001/audit",
                        data=b"{}",
                        headers={
                            "X-Internal-Key": getattr(settings, "INTERNAL_API_KEY", "11121993_29081966"),
                            "Content-Type": "application/json"
                        },
                        method="POST"
                    )
                    urllib.request.urlopen(req, timeout=3)
                    logger.info("Successfully notified debugger_agent for audit.")
                except Exception as ex:
                    logger.debug(f"debugger_agent notification skipped or unreachable: {ex}")

            return {"status": "completed", "result": result_msg, "file": out_path.name}
        else:
            # Если нет файла (например, для "cheapest", если файлы не нашлись)
            task_record.status = "completed"
            task_record.progress_message = result_msg
            db.commit()
            return {"status": "completed", "result": result_msg}

    except Exception as e:
        logger.exception(f"Error executing task {task_record_id}: {e}")
        duration_seconds = int(time.time() - start_time)
        task_record.status = "failed"
        task_record.progress_message = f"Ошибка: {str(e)} (Время выполнения: {duration_seconds} сек)"
        db.commit()
        
        # Отправляем сообщение об ошибке в Telegram
        try:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            asyncio.run(bot.send_message(
                chat_id=user.telegram_id,
                text=f"❌ Произошла ошибка при выполнении задачи {task_record.task_type}:\n<code>{str(e)}</code>",
                parse_mode="HTML"
            ))
        except Exception as telegram_error:
            logger.error(f"Failed to send failure notification to Telegram: {telegram_error}")

        return {"status": "failed", "error": str(e)}
        
    finally:
        db.close()
