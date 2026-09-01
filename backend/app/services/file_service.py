# -*- coding: utf-8 -*-
import os
import shutil
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
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
    def get_distributor_variant_key(filename: str) -> Optional[str]:
        """Определяет ключ дистрибьютора с учетом варианта (100% / 25%)."""
        name_low = filename.lower()
        if "grand" in name_low or "гранд" in name_low:
            variant = "100" if "100" in name_low else "25"
            return f"grand_{variant}"
        if "promotion" in name_low or "промоушен" in name_low or "промоушн" in name_low:
            variant = "100" if "100" in name_low else "25"
            return f"promotion_{variant}"
        if "luxe" in name_low or "люкс" in name_low:
            variant = "100" if "100" in name_low else "25"
            return f"luxe_{variant}"
        if "zenta" in name_low or "зента" in name_low:
            return "zenta"
        if "biotek" in name_low or "биотек" in name_low or "biotech" in name_low:
            return "biotek"
        if "meros" in name_low or "мерос" in name_low:
            return "meros"
        if "choice" in name_low or "чойс" in name_low:
            return "choice"
        if "aero" in name_low or "аэро" in name_low:
            return "aero"
        if "delpharm" in name_low or "дельфарм" in name_low:
            return "delpharm"
        if "asklepiy" in name_low or "асклепий" in name_low:
            return "asklepiy"
        return None

    @staticmethod
    def archive_existing_input_file(db: Session, user_id: int, filename: str, user_upload_dir: Path):
        """Архивирует существующие файлы с тем же именем или того же дистрибьютора в историю."""
        filename = FileService.sanitize_user_filename(filename)
        incoming_dist_key = FileService.get_distributor_variant_key(filename)

        existing_files = db.query(FileRecord).filter(
            FileRecord.user_id == user_id,
            FileRecord.file_type == "input"
        ).all()

        files_to_archive = []
        for ef in existing_files:
            if ef.filename == filename:
                files_to_archive.append(ef)
            elif incoming_dist_key and FileService.get_distributor_variant_key(ef.filename) == incoming_dist_key:
                files_to_archive.append(ef)

        history_dir = user_upload_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)

        for ef in files_to_archive:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            history_filename = f"{Path(ef.filename).stem}_{timestamp}{Path(ef.filename).suffix}"
            history_storage_path = history_dir / history_filename
            
            old_file_path = Path(ef.storage_path)
            if old_file_path.exists():
                try:
                    shutil.move(str(old_file_path), str(history_storage_path))
                except Exception:
                    shutil.copy2(str(old_file_path), str(history_storage_path))
                    try:
                        os.remove(str(old_file_path))
                    except Exception:
                        pass
            
            ef.filename = history_filename
            ef.display_name = history_filename
            ef.storage_path = str(history_storage_path)
            ef.file_type = "input_history"
            
        if files_to_archive:
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
