import secrets
import jwt
from typing import Optional
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models import User

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key"),
    x_target_user_id: Optional[int] = Header(None, alias="X-Target-User-ID"),
    db: Session = Depends(get_db)
) -> User:
    # Проверка внутреннего API-ключа для Агентов (timing-safe check)
    if x_internal_api_key and settings.INTERNAL_API_KEY and secrets.compare_digest(x_internal_api_key, settings.INTERNAL_API_KEY):
        if not x_target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для внутренних запросов требуется указать заголовок X-Target-User-ID"
            )
        user = db.query(User).filter(User.id == x_target_user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Пользователь с ID {x_target_user_id} не найден для авторизации Агента"
            )
        return user

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходим токен авторизации (Bearer token) или X-Internal-API-Key"
        )
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный формат токена"
            )
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден"
            )
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Время сессии истекло"
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен"
        )


def auto_discover_user_files(db: Session, user_id: int):
    """Автоматически сканирует папки пользователя и регистрирует новые файлы/задачи в БД."""
    import os
    import unicodedata
    from datetime import datetime
    from app.models import FileRecord, TaskRecord
    from app.config import settings

    user_upload_dir = settings.UPLOAD_DIR / str(user_id)
    user_output_dir = settings.OUTPUT_DIR / str(user_id)
    
    db_changed = False
    
    # 1. Сканируем входящие прайсы (uploads)
    if user_upload_dir.exists():
        from pathlib import Path
        for filename in os.listdir(user_upload_dir):
            filename_nfc = unicodedata.normalize('NFC', filename)
            file_path = user_upload_dir / filename
            if not file_path.is_file():
                continue
                
            # 1.1. Санируем имя файла для авто-обнаружения (чтобы избежать дублей)
            from app.services.file_service import FileService
            clean_filename = FileService.sanitize_user_filename(filename_nfc)
            
            if clean_filename != filename_nfc:
                clean_path = user_upload_dir / clean_filename
                
                # Если санированный файл уже существует, этот исходный файл считается устаревшим дублем
                if clean_path.exists():
                    history_dir = user_upload_dir / "history"
                    history_dir.mkdir(parents=True, exist_ok=True)
                    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    history_filename = f"{Path(clean_filename).stem}_{timestamp}{Path(clean_filename).suffix}"
                    history_path = history_dir / history_filename
                    
                    try:
                        import shutil
                        shutil.move(str(file_path), str(history_path))
                    except Exception:
                        try:
                            shutil.copy2(str(file_path), str(history_path))
                            os.remove(str(file_path))
                        except Exception:
                            pass
                    
                    # Проверяем, нет ли уже записи в БД для этого дубля в истории
                    existing_hist = db.query(FileRecord).filter(
                        FileRecord.user_id == user_id,
                        FileRecord.filename == history_filename
                    ).first()
                    if not existing_hist:
                        new_file = FileRecord(
                            user_id=user_id,
                            filename=history_filename,
                            display_name=history_filename,
                            file_type='input_history',
                            file_size=history_path.stat().st_size if history_path.exists() else file_path.stat().st_size,
                            storage_path=str(history_path),
                            uploaded_at=datetime.fromtimestamp(file_path.stat().st_mtime)
                        )
                        db.add(new_file)
                        db_changed = True
                    continue
                else:
                    # Если санированного файла на диске нет, переименовываем текущий файл на диске
                    try:
                        os.rename(str(file_path), str(clean_path))
                        filename_nfc = clean_filename
                        file_path = clean_path
                    except Exception:
                        pass
                
            existing = db.query(FileRecord).filter(
                FileRecord.user_id == user_id,
                FileRecord.filename == filename_nfc,
                FileRecord.file_type == 'input'
            ).first()
            
            if not existing:
                new_file = FileRecord(
                    user_id=user_id,
                    filename=filename_nfc,
                    display_name=filename_nfc,
                    file_type='input',
                    file_size=file_path.stat().st_size,
                    storage_path=str(file_path),
                    uploaded_at=datetime.fromtimestamp(file_path.stat().st_mtime)
                )
                db.add(new_file)
                db_changed = True

    # 2. Сканируем сгенерированные отчеты (outputs)
    if user_output_dir.exists():
        for filename in os.listdir(user_output_dir):
            filename_nfc = unicodedata.normalize('NFC', filename)
            file_path = user_output_dir / filename
            if not file_path.is_file() or not filename.endswith('.xlsx'):
                continue
                
            existing_file = db.query(FileRecord).filter(
                FileRecord.user_id == user_id,
                FileRecord.filename == filename_nfc,
                FileRecord.file_type == 'output'
            ).first()
            
            if not existing_file:
                existing_file = FileRecord(
                    user_id=user_id,
                    filename=filename_nfc,
                    display_name=filename_nfc,
                    file_type='output',
                    file_size=file_path.stat().st_size,
                    storage_path=str(file_path),
                    uploaded_at=datetime.fromtimestamp(file_path.stat().st_mtime)
                )
                db.add(existing_file)
                db_changed = True
                
            existing_task = db.query(TaskRecord).filter(
                TaskRecord.user_id == user_id,
                TaskRecord.result_file_path == str(file_path)
            ).first()
            
            if not existing_task:
                task_type = 'svodny_horizontal'
                task_name_ru = 'Сводный прайс'
                if 'верт' in filename_nfc.lower():
                    task_type = 'svodny_vertical'
                    task_name_ru = 'Сводный прайс (верт.)'
                elif 'ассортимент' in filename_nfc.lower():
                    task_type = 'assortment'
                    task_name_ru = 'Анализ ассортимента'
                elif 'поставщик' in filename_nfc.lower():
                    task_type = 'best_suppliers'
                    task_name_ru = 'Анализ лучших поставщиков'
                elif 'миним' in filename_nfc.lower() or 'дешев' in filename_nfc.lower():
                    task_type = 'cheapest'
                    task_name_ru = 'Подсветка минимальных цен'
                    
                new_task = TaskRecord(
                    user_id=user_id,
                    task_type=task_type,
                    status='completed',
                    progress_message=f'{task_name_ru} успешно собран (импортирован с диска).',
                    result_file_path=str(file_path),
                    created_at=datetime.fromtimestamp(file_path.stat().st_mtime)
                )
                db.add(new_task)
                db_changed = True

    # 2.5 Сканируем подпапку отчетов о продажах (outputs/user_id/sales и outputs/sales)
    sales_dirs = [user_output_dir / "sales", settings.OUTPUT_DIR / "sales"]
    for s_dir in sales_dirs:
        if s_dir.exists():
            for filename in os.listdir(s_dir):
                filename_nfc = unicodedata.normalize('NFC', filename)
                file_path = s_dir / filename
                if not file_path.is_file() or not filename.endswith('.xlsx'):
                    continue
                    
                existing_sales_file = db.query(FileRecord).filter(
                    FileRecord.user_id == user_id,
                    FileRecord.filename == filename_nfc,
                    FileRecord.file_type == 'sales'
                ).first()
                
                if not existing_sales_file:
                    existing_sales_file = FileRecord(
                        user_id=user_id,
                        filename=filename_nfc,
                        display_name=filename_nfc,
                        file_type='sales',
                        file_size=file_path.stat().st_size,
                        storage_path=str(file_path),
                        uploaded_at=datetime.fromtimestamp(file_path.stat().st_mtime)
                    )
                    db.add(existing_sales_file)
                    db_changed = True

    # 3. Удаление записей о несуществующих на диске файлах (синхронизация)
    all_files = db.query(FileRecord).filter(FileRecord.user_id == user_id).all()
    for f in all_files:
        norm_path = unicodedata.normalize('NFC', f.storage_path)
        if not os.path.exists(norm_path):
            db.delete(f)
            db_changed = True

    all_tasks = db.query(TaskRecord).filter(
        TaskRecord.user_id == user_id,
        TaskRecord.status == 'completed',
        TaskRecord.result_file_path != None
    ).all()
    for t in all_tasks:
        norm_path = unicodedata.normalize('NFC', t.result_file_path)
        if not os.path.exists(norm_path):
            db.delete(t)
            db_changed = True

    # 4. Дедупликация (удаление старых записей БД при перезаписи файлов с тем же именем)
    # Оставляем только самую новую FileRecord для каждого уникального storage_path
    output_files = db.query(FileRecord).filter(
        FileRecord.user_id == user_id,
        FileRecord.file_type == 'output'
    ).order_by(FileRecord.uploaded_at.desc(), FileRecord.id.desc()).all()
    
    seen_file_paths = set()
    for f in output_files:
        norm_path = unicodedata.normalize('NFC', f.storage_path)
        if norm_path in seen_file_paths:
            db.delete(f)
            db_changed = True
        else:
            seen_file_paths.add(norm_path)

    # Оставляем только самую новую завершенную TaskRecord для каждого уникального result_file_path
    completed_tasks = db.query(TaskRecord).filter(
        TaskRecord.user_id == user_id,
        TaskRecord.status == 'completed',
        TaskRecord.result_file_path != None
    ).order_by(TaskRecord.created_at.desc(), TaskRecord.id.desc()).all()
    
    seen_task_paths = set()
    for t in completed_tasks:
        norm_path = unicodedata.normalize('NFC', t.result_file_path)
        if norm_path in seen_task_paths:
            db.delete(t)
            db_changed = True
        else:
            seen_task_paths.add(norm_path)

    if db_changed:
        db.commit()
