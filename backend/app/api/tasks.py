# -*- coding: utf-8 -*-
import os
from typing import List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, FileRecord, TaskRecord
from app.schemas import TaskRecordSchema, TaskCreateSchema
from app.api.dependencies import get_current_user
from app.tasks import run_pipeline_task

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.get("", response_model=List[TaskRecordSchema])
def get_tasks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Возвращает историю запусков задач пользователя."""
    # 1. Авто-обнаружение и синхронизация задач/файлов с диском
    from app.api.dependencies import auto_discover_user_files
    auto_discover_user_files(db, current_user.id)

    return db.query(TaskRecord).filter(TaskRecord.user_id == current_user.id).order_by(TaskRecord.created_at.desc()).all()


@router.delete("/errors")
def clear_failed_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаляет все ошибочные (failed) задачи пользователя."""
    failed_tasks = db.query(TaskRecord).filter(
        TaskRecord.user_id == current_user.id,
        TaskRecord.status == "failed"
    ).all()
    
    count = len(failed_tasks)
    for t in failed_tasks:
        db.delete(t)
        
    db.commit()
    return {"message": f"Успешно удалено {count} задач с ошибками"}


@router.post("", response_model=TaskRecordSchema)
def create_task(
    task_data: TaskCreateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Инициирует выполнение новой фоновой задачи."""
    task_type = task_data.task_type
    is_automated = task_data.is_automated
    file_ids = task_data.file_ids
    
    # Проверяем файлы
    if task_type not in ["cheapest", "best_suppliers"]:
        if file_ids:
            # Проверяем, что переданные file_ids действительно существуют, принадлежат юзеру и имеют тип input
            valid_files_count = db.query(FileRecord).filter(
                FileRecord.id.in_(file_ids),
                FileRecord.user_id == current_user.id,
                FileRecord.file_type == "input"
            ).count()
            if valid_files_count != len(file_ids):
                raise HTTPException(
                    status_code=400,
                    detail="Некоторые из указанных файлов не найдены или не принадлежат пользователю"
                )
        else:
            input_files_count = db.query(FileRecord).filter(
                FileRecord.user_id == current_user.id,
                FileRecord.file_type == "input"
            ).count()
            if input_files_count == 0:
                raise HTTPException(status_code=400, detail="Загрузите хотя бы один файл Excel для анализа")
    else:
        output_files_count = db.query(FileRecord).filter(
            FileRecord.user_id == current_user.id,
            FileRecord.file_type == "output",
            FileRecord.filename.like("%Сводный%")
        ).count()
        if output_files_count == 0:
            raise HTTPException(status_code=400, detail="Сначала необходимо собрать горизонтальный или вертикальный сводный прайс")

    new_task = TaskRecord(
        user_id=current_user.id,
        task_type=task_type,
        status="pending",
        is_automated=is_automated,
        file_ids=file_ids,
        progress_message="Добавление в очередь..."
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    
    # Запуск Celery задачи с сохранением ID
    celery_task = run_pipeline_task.delay(new_task.id)
    new_task.celery_task_id = celery_task.id
    db.commit()
    
    return new_task


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Останавливает (отменяет) запущенную фоновую задачу."""
    task = db.query(TaskRecord).filter(
        TaskRecord.id == task_id,
        TaskRecord.user_id == current_user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
        
    if task.status not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Можно остановить только активные задачи")
        
    if task.celery_task_id:
        from app.worker import celery_app
        try:
            # Отменяем задачу в Celery и прерываем выполнение
            celery_app.control.revoke(task.celery_task_id, terminate=True, signal='SIGKILL')
        except Exception as e:
            print(f"Error revoking celery task {task.celery_task_id}: {e}")
        
    # Обновляем статус в базе данных
    task.status = "failed"
    task.progress_message = "Задача остановлена пользователем."
    db.commit()
    
    return {"message": "Задача успешно остановлена"}


@router.get("/{task_id}", response_model=TaskRecordSchema)
def get_task_status(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает статус конкретной задачи."""
    task = db.query(TaskRecord).filter(TaskRecord.id == task_id, TaskRecord.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаляет задачу и связанный с ней файл отчета с диска."""
    task = db.query(TaskRecord).filter(
        TaskRecord.id == task_id,
        TaskRecord.user_id == current_user.id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
        
    if task.status in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Нельзя удалить выполняющуюся задачу")
        
    # Удаляем файл отчета с диска, если он существует
    if task.result_file_path:
        file_path = Path(task.result_file_path)
        try:
            if file_path.is_file():
                file_path.unlink()
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            
    db.delete(task)
    db.commit()
    
    return {"message": "Задача и файл отчета успешно удалены"}
