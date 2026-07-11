# -*- coding: utf-8 -*-
import os
import shutil
import re
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from app.models import FileRecord

class FileService:
    @staticmethod
    def sanitize_user_filename(filename: str) -> str:
        """Очищает имя файла от путей и недопустимых спецсимволов для безопасности (Path Traversal)."""
        # Получаем только имя файла без путей
        base_name = Path(filename).name
        # Оставляем только буквы, цифры, дефис, подчеркивание, точку и пробелы
        clean_name = re.sub(r"[^\w\s.-]", "", base_name)
        # Заменяем множественные пробелы на одиночные
        clean_name = " ".join(clean_name.split())
        if not clean_name:
            clean_name = "uploaded_file.xlsx"
        return clean_name

    @staticmethod
    def archive_existing_input_file(db: Session, user_id: int, filename: str, user_upload_dir: Path):
        """Если активный файл с таким именем уже существует, переносит его в историю на диске и в БД."""
        filename = FileService.sanitize_user_filename(filename)
        existing_file = db.query(FileRecord).filter(
            FileRecord.user_id == user_id,
            FileRecord.filename == filename,
            FileRecord.file_type == "input"
        ).first()

        if existing_file:
            history_dir = user_upload_dir / "history"
            history_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            history_filename = f"{Path(filename).stem}_{timestamp}{Path(filename).suffix}"
            history_storage_path = history_dir / history_filename
            
            old_file_path = Path(existing_file.storage_path)
            if old_file_path.exists():
                try:
                    shutil.move(str(old_file_path), str(history_storage_path))
                except Exception:
                    shutil.copy2(str(old_file_path), str(history_storage_path))
                    os.remove(str(old_file_path))
            
            existing_file.filename = history_filename
            existing_file.display_name = history_filename
            existing_file.storage_path = str(history_storage_path)
            existing_file.file_type = "input_history"
            db.commit()

    @staticmethod
    def register_input_file_db(
        db: Session,
        user_id: int,
        filename: str,
        file_size: int,
        storage_path: Path,
        read_preset: str = ""
    ) -> FileRecord:
        """Регистрирует новый входящий файл в базе данных."""
        filename = FileService.sanitize_user_filename(filename)
        new_file = FileRecord(
            user_id=user_id,
            filename=filename,
            display_name=filename,
            file_type="input",
            read_preset=read_preset,
            file_size=file_size,
            storage_path=str(storage_path)
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        return new_file
