# -*- coding: utf-8 -*-
import os
import shutil
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import User, FileRecord
from app.schemas import FileRecordSchema, FileUpdateSchema
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/files", tags=["files"])

@router.get("", response_model=List[FileRecordSchema])
def get_files(
    file_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает список файлов пользователя (входящие прайсы или отчеты)."""
    # 1. Авто-обнаружение и синхронизация файлов на диске с БД
    from app.api.dependencies import auto_discover_user_files
    auto_discover_user_files(db, current_user.id)

    query = db.query(FileRecord).filter(FileRecord.user_id == current_user.id)
    if file_type:
        query = query.filter(FileRecord.file_type == file_type)
    return query.order_by(FileRecord.uploaded_at.desc()).all()


@router.post("/upload", response_model=FileRecordSchema)
async def upload_file(
    file: UploadFile = File(...),
    read_preset: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Загружает файл Excel на сервер и регистрирует его в базе данных."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".xlsx", ".xls"]:
        raise HTTPException(status_code=400, detail="Разрешены только файлы Excel (.xlsx, .xls)")

    from app.services.file_service import FileService

    clean_filename = FileService.sanitize_user_filename(file.filename)
    user_upload_dir = settings.UPLOAD_DIR / str(current_user.id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = user_upload_dir / clean_filename

    # 1. Архивируем старый файл, если он существует
    FileService.archive_existing_input_file(db, current_user.id, clean_filename, user_upload_dir)

    # 2. Сохраняем новый файл физически
    with storage_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    file_size = storage_path.stat().st_size

    # 3. Регистрируем новый файл в БД
    new_file = FileService.register_input_file_db(
        db=db,
        user_id=current_user.id,
        filename=clean_filename,
        file_size=file_size,
        storage_path=storage_path,
        read_preset=read_preset
    )
    return new_file


@router.put("/{file_id}", response_model=FileRecordSchema)
def update_file_preset(
    file_id: int,
    file_data: FileUpdateSchema,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Обновляет шаблон парсера (read_preset) для файла."""
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    file_record.read_preset = file_data.read_preset
    db.commit()
    db.refresh(file_record)
    return file_record


@router.delete("/clear")
def clear_all_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаляет все загруженные прайс-листы пользователя (input файлы) с диска и БД."""
    input_files = db.query(FileRecord).filter(
        FileRecord.user_id == current_user.id,
        FileRecord.file_type == "input"
    ).all()
    
    for f in input_files:
        try:
            if os.path.exists(f.storage_path):
                os.remove(f.storage_path)
        except Exception:
            pass
        db.delete(f)
        
    db.commit()
    return {"message": "Все загруженные прайс-листы успешно удалены"}


@router.get("/purge-preview")
def purge_preview(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    month: Optional[str] = None,
    file_type: Optional[str] = "all",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Предварительный просмотр файлов, которые будут удалены за указанный период."""
    from datetime import datetime, timedelta

    query = db.query(FileRecord).filter(FileRecord.user_id == current_user.id)
    if file_type and file_type != "all":
        if file_type == "input":
            query = query.filter(FileRecord.file_type.in_(["input", "input_history"]))
        else:
            query = query.filter(FileRecord.file_type == file_type)

    if month:
        months_list = [m.strip() for m in month.split(",") if m.strip()]
        for m_str in months_list:
            try:
                parts = m_str.split(".")
                if len(parts) == 2:
                    m_num, y_num = int(parts[0]), int(parts[1])
                    start_dt = datetime(y_num, m_num, 1)
                    if m_num == 12:
                        end_dt = datetime(y_num + 1, 1, 1)
                    else:
                        end_dt = datetime(y_num, m_num + 1, 1)
                    query = query.filter(FileRecord.uploaded_at >= start_dt, FileRecord.uploaded_at < end_dt)
            except Exception:
                pass
    elif date_from or date_to:
        if date_from:
            try:
                dt_from = datetime.strptime(date_from, "%Y-%m-%d")
                query = query.filter(FileRecord.uploaded_at >= dt_from)
            except ValueError:
                try:
                    dt_from = datetime.strptime(date_from, "%d.%m.%Y")
                    query = query.filter(FileRecord.uploaded_at >= dt_from)
                except Exception:
                    pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(FileRecord.uploaded_at < dt_to)
            except ValueError:
                try:
                    dt_to = datetime.strptime(date_to, "%d.%m.%Y") + timedelta(days=1)
                    query = query.filter(FileRecord.uploaded_at < dt_to)
                except Exception:
                    pass

    files_found = query.all()
    total_bytes = 0
    file_list = []
    for f in files_found:
        size = f.file_size or 0
        if os.path.exists(f.storage_path):
            try:
                size = os.path.getsize(f.storage_path)
            except Exception:
                pass
        total_bytes += size
        file_list.append({
            "id": f.id,
            "filename": f.display_name or f.filename,
            "file_type": f.file_type,
            "size_mb": round(size / (1024 * 1024), 2),
            "uploaded_at": f.uploaded_at.isoformat()
        })

    return {
        "count": len(files_found),
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "files": file_list
    }


@router.delete("/purge")
def purge_files_by_period(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    month: Optional[str] = None,
    file_type: Optional[str] = "all",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Очищает файлы за выбранный период дат или месяцев с диска и из БД."""
    from datetime import datetime, timedelta

    query = db.query(FileRecord).filter(FileRecord.user_id == current_user.id)
    if file_type and file_type != "all":
        if file_type == "input":
            query = query.filter(FileRecord.file_type.in_(["input", "input_history"]))
        else:
            query = query.filter(FileRecord.file_type == file_type)

    if month:
        months_list = [m.strip() for m in month.split(",") if m.strip()]
        for m_str in months_list:
            try:
                parts = m_str.split(".")
                if len(parts) == 2:
                    m_num, y_num = int(parts[0]), int(parts[1])
                    start_dt = datetime(y_num, m_num, 1)
                    if m_num == 12:
                        end_dt = datetime(y_num + 1, 1, 1)
                    else:
                        end_dt = datetime(y_num, m_num + 1, 1)
                    query = query.filter(FileRecord.uploaded_at >= start_dt, FileRecord.uploaded_at < end_dt)
            except Exception:
                pass
    elif date_from or date_to:
        if date_from:
            try:
                dt_from = datetime.strptime(date_from, "%Y-%m-%d")
                query = query.filter(FileRecord.uploaded_at >= dt_from)
            except ValueError:
                try:
                    dt_from = datetime.strptime(date_from, "%d.%m.%Y")
                    query = query.filter(FileRecord.uploaded_at >= dt_from)
                except Exception:
                    pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(FileRecord.uploaded_at < dt_to)
            except ValueError:
                try:
                    dt_to = datetime.strptime(date_to, "%d.%m.%Y") + timedelta(days=1)
                    query = query.filter(FileRecord.uploaded_at < dt_to)
                except Exception:
                    pass

    files_to_delete = query.all()
    if not files_to_delete:
        return {
            "message": "Файлы за указанный период не найдены",
            "deleted_count": 0,
            "freed_mb": 0.0
        }

    total_bytes = 0
    deleted_count = 0
    deleted_filenames = []

    for f in files_to_delete:
        f_size = f.file_size or 0
        if os.path.exists(f.storage_path):
            try:
                f_size = os.path.getsize(f.storage_path)
                os.remove(f.storage_path)
            except Exception:
                pass
        total_bytes += f_size
        deleted_count += 1
        deleted_filenames.append(f.display_name or f.filename)
        db.delete(f)

    db.commit()
    freed_mb = round(total_bytes / (1024 * 1024), 2)

    return {
        "message": f"Успешно удалено {deleted_count} файлов за указанный период.",
        "deleted_count": deleted_count,
        "freed_mb": freed_mb,
        "deleted_filenames": deleted_filenames
    }


@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаляет файл с сервера и из БД."""
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="Файл не найден")
        
    try:
        if os.path.exists(file_record.storage_path):
            os.remove(file_record.storage_path)
    except Exception as e:
        pass  # Пропускаем, если файл уже удален с диска
        
    db.delete(file_record)
    db.commit()
    return {"message": "Файл успешно удален"}


@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Скачивает файл."""
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record or not os.path.exists(file_record.storage_path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")
        
    return FileResponse(
        path=file_record.storage_path,
        filename=file_record.display_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/download_by_name/{filename}")
def download_file_by_name(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Скачивает файл по его имени."""
    file_record = db.query(FileRecord).filter(
        FileRecord.filename == filename,
        FileRecord.user_id == current_user.id
    ).first()
    if not file_record or not os.path.exists(file_record.storage_path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")
        
    return FileResponse(
        path=file_record.storage_path,
        filename=file_record.display_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
