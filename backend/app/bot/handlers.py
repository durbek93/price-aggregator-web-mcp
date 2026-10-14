# -*- coding: utf-8 -*-
import logging
import os
import urllib.request
import urllib.error
import asyncio
from datetime import datetime
import re
from typing import List, Optional, Dict
from aiogram import Router, Bot, F, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import User, FileRecord, TaskRecord
from sqlalchemy import or_, and_
from app.tasks import run_pipeline_task
from app.bot.keyboards import get_main_keyboard
from app.bot.utils import generate_magic_link, get_or_create_user

logger = logging.getLogger(__name__)

router = Router()

@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Обработчик команды /start."""
    tg_user = message.from_user
    user = get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name
    )
    
    magic_link = generate_magic_link(user.id, tg_user.id)
    
    await message.answer(
        f"Привет, {html.bold(tg_user.full_name)}!\n\n"
        f"Я бот для работы со сводными прайс-листами Excel. Вы можете:\n"
        f"1. Отправлять мне файлы прайс-листов Excel (форматы .xlsx, .xls).\n"
        f"2. Запускать анализ файлов прямо отсюда с помощью меню ниже.\n"
        f"3. Авторизоваться в веб-интерфейсе для тонкой настройки колонок, каталога брендов и просмотра графиков.\n\n"
        f"🔗 {html.bold('Ваша ссылка для входа на сайт:')}\n{magic_link}\n"
        f"_(Действительна 15 минут)_",
        reply_markup=get_main_keyboard(),
        disable_web_page_preview=True
    )


@router.message(Command("menu"))
async def command_menu_handler(message: Message) -> None:
    """Выводит главное меню."""
    await message.answer("Выберите нужное действие из меню ниже:", reply_markup=get_main_keyboard())


@router.message(Command("link"))
async def command_link_handler(message: Message) -> None:
    """Генерирует новую ссылку авторизации."""
    tg_user = message.from_user
    user = get_or_create_user(telegram_id=tg_user.id)
    magic_link = generate_magic_link(user.id, tg_user.id)
    
    await message.answer(
        f"🔗 {html.bold('Ваша ссылка для входа на сайт:')}\n{magic_link}",
        disable_web_page_preview=True
    )


@router.message(F.document)
async def handle_document_upload(message: Message, bot: Bot) -> None:
    """Обрабатывает загрузку Excel файлов от пользователя."""
    doc = message.document
    filename = doc.file_name
    suffix = Path(filename).suffix.lower()
    
    if suffix not in [".xlsx", ".xls"]:
        await message.answer("⚠️ Пожалуйста, загружайте только файлы таблиц Excel (.xlsx или .xls).")
        return
        
    tg_user = message.from_user
    user = get_or_create_user(telegram_id=tg_user.id)
    
    # Создаем папку для загрузок пользователя
    from app.services.file_service import FileService
    clean_filename = FileService.sanitize_user_filename(filename)

    user_upload_dir = settings.UPLOAD_DIR / str(user.id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Путь сохранения файла на сервере
    storage_path = user_upload_dir / clean_filename
    
    # Записываем информацию о файле в базу данных
    db = SessionLocal()
    try:
        # Проверяем, существует ли уже активный файл с таким именем у этого пользователя
        has_existing = db.query(FileRecord).filter(
            FileRecord.user_id == user.id,
            FileRecord.filename == clean_filename,
            FileRecord.file_type == "input"
        ).first() is not None

        # 1. Архивируем старый файл, если он существует
        FileService.archive_existing_input_file(db, user.id, clean_filename, user_upload_dir)
        msg_text = (
            f"🔄 Файл {html.bold(clean_filename)} успешно обновлен на сервере (предыдущая версия сохранена в историю)."
            if has_existing else f"📥 Файл {html.bold(clean_filename)} успешно сохранен на сервере."
        )
            
        # 2. Скачиваем новый файл через Telegram Bot API
        file_info = await bot.get_file(doc.file_id)
        await bot.download_file(file_info.file_path, destination=storage_path)
        
        # 3. Создаем запись для нового активного файла
        FileService.register_input_file_db(
            db=db,
            user_id=user.id,
            filename=clean_filename,
            file_size=doc.file_size,
            storage_path=storage_path
        )
        
        # Получаем количество всех текущих файлов
        count = db.query(FileRecord).filter(
            FileRecord.user_id == user.id,
            FileRecord.file_type == "input"
        ).count()
        
        await message.answer(
            f"{msg_text}\nВсего файлов для обработки: {html.bold(count)}.\n\n"
            f"Используйте меню или команду /menu для запуска анализа.",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Error saving uploaded file info to DB: {e}")
        await message.answer("❌ Произошла ошибка при регистрации файла в базе данных.")
    finally:
        db.close()


@router.callback_query(F.data.startswith("run:"))
async def handle_run_task_callback(callback: CallbackQuery) -> None:
    """Обрабатывает нажатия кнопок запуска фонового анализа."""
    task_type = callback.data.split(":")[1]
    tg_user = callback.from_user
    user = get_or_create_user(telegram_id=tg_user.id)
    
    db = SessionLocal()
    try:
        # Проверяем наличие входных файлов перед запуском (кроме cheapest и best_suppliers,
        # которые работают на основе уже сгенерированных сводных прайсов)
        if task_type not in ["cheapest", "best_suppliers"]:
            input_files_count = db.query(FileRecord).filter(
                FileRecord.user_id == user.id,
                FileRecord.file_type == "input"
            ).count()
            if input_files_count == 0:
                await callback.answer("⚠️ Сначала отправьте мне хотя бы один прайс Excel!", show_alert=True)
                return
        else:
            # Для cheapest / best_suppliers проверяем наличие ранее созданных сводных прайсов
            output_files_count = db.query(FileRecord).filter(
                FileRecord.user_id == user.id,
                FileRecord.file_type == "output",
                FileRecord.filename.like("%Сводный%")
            ).count()
            if output_files_count == 0:
                await callback.answer("⚠️ Сначала запустите сборку Сводного прайса!", show_alert=True)
                return

        # Создаем запись о задаче в БД
        task_record = TaskRecord(
            user_id=user.id,
            task_type=task_type,
            status="pending",
            progress_message="Постановка задачи в очередь..."
        )
        db.add(task_record)
        db.commit()
        db.refresh(task_record)
        
        # Запускаем Celery-таску асинхронно
        run_pipeline_task.delay(task_record.id)
        
        await callback.answer("🚀 Задача запущена в фоновом режиме!")
        await callback.message.answer(
            f"⏳ Задача {html.bold(task_type)} поставлена в очередь.\n"
            f"Я сообщу вам и пришлю файл отчета, как только обработка завершится!"
        )
    except Exception as e:
        logger.error(f"Error starting celery task from bot: {e}")
        await callback.answer("❌ Не удалось запустить задачу.")
    finally:
        db.close()


@router.callback_query(F.data == "collect:fergana")
async def handle_collect_fergana_callback(callback: CallbackQuery) -> None:
    """Запускает сбор прайсов по 17 оптовикам Ферганской долины через Scout Agent."""
    tg_user = callback.from_user
    if tg_user.id not in settings.allowed_telegram_ids_set:
        await callback.answer("⛔ У вас нет доступа к этой команде.", show_alert=True)
        return

    await callback.answer("🍇 Запущен сбор прайсов Ферганской долины...")
    sent_msg = await callback.message.answer(
        "🍇 <b>[ФЕРГАНСКАЯ ДОЛИНА]</b> Начинаю опрос каналов 17 местных оптовиков...\n"
        "По завершении сводный прайс будет собран и отправлен в чат."
    )

    try:
        import json
        url = "http://scout_agent:8080/collect_fergana"
        payload = json.dumps({
            "chat_id": callback.message.chat.id,
            "message_id": sent_msg.message_id
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("X-Internal-API-Key", settings.INTERNAL_API_KEY)
        req.add_header("Content-Type", "application/json")

        loop = asyncio.get_running_loop()
        def _send_request():
            with urllib.request.urlopen(req, timeout=10.0) as response:
                return response.status, response.read().decode()

        status, _ = await loop.run_in_executor(None, _send_request)
        if status != 200:
            await callback.message.answer("❌ Ошибка при обращении к Агенту-Сборщику.")
    except Exception as e:
        logger.exception(f"Exception triggering Fergana collection: {e}")
        await callback.message.answer(f"❌ Не удалось связаться с Агентом-Сборщиком: {e}")


@router.callback_query(F.data == "clear_files")
async def handle_clear_files_callback(callback: CallbackQuery) -> None:
    """Удаляет все файлы пользователя с сервера и из базы данных."""
    tg_user = callback.from_user
    user = get_or_create_user(telegram_id=tg_user.id)
    
    db = SessionLocal()
    try:
        # Удаляем записи файлов
        files = db.query(FileRecord).filter(FileRecord.user_id == user.id).all()
        for f in files:
            try:
                if os.path.exists(f.storage_path):
                    os.remove(f.storage_path)
            except Exception as e:
                logger.error(f"Error deleting physical file {f.storage_path}: {e}")
            db.delete(f)
            
        db.commit()
        await callback.answer("🧹 Все файлы очищены!", show_alert=True)
        await callback.message.answer("Все ваши загруженные прайс-листы и готовые отчеты были успешно удалены с сервера.")
    except Exception as e:
        logger.error(f"Error clearing user files: {e}")
        await callback.answer("❌ Ошибка при очистке файлов.")
    finally:
        db.close()


@router.callback_query(F.data.startswith("confirm_purge:"))
async def handle_confirm_purge_callback(callback: CallbackQuery) -> None:
    """Подтверждение физической очистки файлов за указанный период."""
    tg_user = callback.from_user
    user = get_or_create_user(telegram_id=tg_user.id)
    
    if tg_user.id not in settings.allowed_telegram_ids_set:
        await callback.answer("❌ У вас нет прав для выполнения этой операции.", show_alert=True)
        return
        
    period_token = callback.data.split(":", 1)[1]
    months_list = period_token.split("-")
    
    db = SessionLocal()
    try:
        from datetime import datetime
        user_ids = [user.id] if user.id == 1 else [user.id, 1]
        query = db.query(FileRecord).filter(FileRecord.user_id.in_(user_ids))
        
        # Фильтруем по месяцам
        month_conditions = []
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
                    month_conditions.append(and_(FileRecord.uploaded_at >= start_dt, FileRecord.uploaded_at < end_dt))
            except Exception:
                pass
                
        if month_conditions:
            query = query.filter(or_(*month_conditions))
            files_to_delete = query.all()
        else:
            files_to_delete = []

        if not files_to_delete:
            await callback.answer("ℹ️ Файлы не найдены.")
            await callback.message.edit_text("ℹ️ Файлы за выбранный период не найдены или уже удалены.")
            return

        total_bytes = 0
        deleted_count = 0
        for f in files_to_delete:
            f_size = f.file_size or 0
            if os.path.exists(f.storage_path):
                try:
                    f_size = os.path.getsize(f.storage_path)
                    os.remove(f.storage_path)
                except Exception as e:
                    logger.error(f"Failed to delete file {f.storage_path}: {e}")
            total_bytes += f_size
            deleted_count += 1
            db.delete(f)

        db.commit()
        freed_mb = round(total_bytes / (1024 * 1024), 2)
        months_display = ", ".join(months_list)
        
        await callback.answer("✅ Очистка завершена!", show_alert=True)
        await callback.message.edit_text(
            f"✅ {html.bold('Очистка памяти выполнена успешно!')}\n\n"
            f"📅 Период: {html.code(months_display)}\n"
            f"🗑 Удалено файлов: {html.bold(str(deleted_count))} шт.\n"
            f"💾 Освобождено диска: {html.bold(str(freed_mb))} МБ"
        )
    except Exception as e:
        logger.exception(f"Error during purge execution: {e}")
        await callback.answer("❌ Ошибка при удалении файлов.", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data == "cancel_purge")
async def handle_cancel_purge_callback(callback: CallbackQuery) -> None:
    """Отмена процедуры очистки памяти."""
    await callback.answer("Операция отменена.")
    await callback.message.edit_text("❌ Операция очистки памяти отменена пользователем.")


def parse_purge_months(text: str) -> List[str]:
    """Извлекает список месяцев формата MM.YYYY из текста или названий месяцев на русском."""
    months = []
    # 1. Поиск совпадений вида 05.2026 или 05/2026
    for m, y in re.findall(r"\b(0[1-9]|1[0-2])[\.\/](20\d{2})\b", text):
        months.append(f"{m}.{y}")

    # 2. Поиск по русским названиям месяцев
    month_map = {
        "январ": "01", "феврал": "02", "март": "03", "апрел": "04",
        "май": "05", "мая": "05", "июн": "06", "июл": "07",
        "август": "08", "сентябр": "09", "октябр": "10", "ноябр": "11", "декабр": "12"
    }
    years = re.findall(r"\b(20\d{2})\b", text)
    year = years[0] if years else "2026"
    for name, num in month_map.items():
        if name in text.lower():
            m_str = f"{num}.{year}"
            if m_str not in months:
                months.append(m_str)
    return months


@router.message(F.text)
async def handle_bot_mention_in_group(message: Message) -> None:
    """Обрабатывает команды и упоминания бота-репортера от разрешенных пользователей."""
    text = (message.text or "").strip()
    low_text = text.lower()
    
    # 1. Проверяем команды очистки памяти (/clean, /purge, "очисти память")
    is_clean_trigger = (
        low_text.startswith(("/clean", "/purge", "/clean@lightprice_aggr_bot", "/purge@lightprice_aggr_bot")) or
        "очисти память" in low_text or
        "очистить память" in low_text or
        "удали прайсы за" in low_text
    )
    
    if is_clean_trigger:
        tg_user = message.from_user
        if not tg_user or tg_user.id not in settings.allowed_telegram_ids_set:
            logger.warning(f"Unauthorized clean attempt from user {tg_user.id if tg_user else 'unknown'}")
            return
            
        months = parse_purge_months(text)
        if not months:
            await message.reply(
                "ℹ️ Укажите месяц или период для очистки в формате MM.YYYY.\n\n"
                "Примеры использования:\n"
                "• `/clean 05.2026` (за май 2026)\n"
                "• `/clean 05.2026-06.2026` (за май и июнь 2026)\n"
                "• `/clean май и июнь 2026`",
                parse_mode="Markdown"
            )
            return

        months_display = ", ".join(months)
        user = get_or_create_user(telegram_id=tg_user.id)
        
        # Расчет предварительного объема для удаления
        db = SessionLocal()
        try:
            from datetime import datetime
            user_ids = [user.id] if user.id == 1 else [user.id, 1]
            query = db.query(FileRecord).filter(FileRecord.user_id.in_(user_ids))
            month_conditions = []
            for m_str in months:
                try:
                    parts = m_str.split(".")
                    if len(parts) == 2:
                        m_num, y_num = int(parts[0]), int(parts[1])
                        start_dt = datetime(y_num, m_num, 1)
                        end_dt = datetime(y_num + 1, 1, 1) if m_num == 12 else datetime(y_num, m_num + 1, 1)
                        month_conditions.append(and_(FileRecord.uploaded_at >= start_dt, FileRecord.uploaded_at < end_dt))
                except Exception:
                    pass
                    
            if month_conditions:
                query = query.filter(or_(*month_conditions))
                files_found = query.all()
            else:
                files_found = []

            if not files_found:
                await message.reply(f"ℹ️ Файлы за период {html.code(months_display)} не найдены в базе данных.")
                return
                
            total_bytes = sum(f.file_size or 0 for f in files_found)
            total_mb = round(total_bytes / (1024 * 1024), 2)
            
            period_token = "-".join(months)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚠️ Подтвердить удаление", callback_data=f"confirm_purge:{period_token}"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_purge")
                ]
            ])
            
            await message.reply(
                f"⚠️ {html.bold('Подтверждение очистки дисковой памяти')}\n\n"
                f"📅 Период: {html.code(months_display)}\n"
                f"📦 Найдено файлов: {html.bold(str(len(files_found)))} шт.\n"
                f"💾 Занимаемый объем: {html.bold(str(total_mb))} МБ\n\n"
                f"Вы действительно хотите удалить эти файлы с диска и из БД?",
                reply_markup=keyboard
            )
            return
        except Exception as e:
            logger.exception(f"Error preparing purge preview: {e}")
            await message.reply("❌ Ошибка при подготовке сведений об очистке.")
            return
        finally:
            db.close()

    # 2. Проверяем команды быстрой сборки из сохраненных прайсов
    is_just_collect_fergana = (
        low_text.startswith(("/just_collect_fergana", "/build_fergana")) or
        "собери ферган" in low_text or
        ("ферган" in low_text and ("только собрать" in low_text or "быстрая сборка" in low_text))
    )
    is_just_collect_republic = (
        low_text.startswith(("/just_collect", "/build_svodny", "/just_aggregate")) or
        "только собрать" in low_text or
        "быстрая сборка" in low_text or
        "собери из существующих" in low_text or
        "собери сводный" in low_text
    )

    if is_just_collect_fergana:
        tg_user = message.from_user
        if not tg_user or tg_user.id not in settings.allowed_telegram_ids_set:
            logger.warning(f"User {tg_user.id if tg_user else 'unknown'} tried to trigger just_collect_fergana but is not allowed.")
            return
            
        user = get_or_create_user(telegram_id=tg_user.id)
        db = SessionLocal()
        try:
            target_user = user
            input_files = db.query(FileRecord).filter(
                FileRecord.user_id == target_user.id,
                FileRecord.file_type == "input",
                FileRecord.storage_path.like("%/fergana/%")
            ).all()
            
            if not input_files and target_user.id != 1:
                input_files = db.query(FileRecord).filter(
                    FileRecord.user_id == 1,
                    FileRecord.file_type == "input",
                    FileRecord.storage_path.like("%/fergana/%")
                ).all()
                if input_files:
                    target_user = db.query(User).filter(User.id == 1).first() or target_user

            fergana_dir = settings.UPLOAD_DIR / str(target_user.id) / "fergana"
            if not input_files and fergana_dir.exists():
                for fpath in fergana_dir.glob("*.xls*"):
                    if fpath.is_file() and not fpath.name.startswith("~"):
                        from app.services.file_service import FileService
                        clean_fn = FileService.sanitize_user_filename(fpath.name)
                        rec = FileService.register_input_file_db(
                            db=db,
                            user_id=target_user.id,
                            filename=clean_fn,
                            file_size=fpath.stat().st_size,
                            storage_path=fpath,
                            read_preset=""
                        )
                        input_files.append(rec)
            
            if not input_files:
                await message.reply(
                    "⚠️ <b>В папке Ферганской долины нет сохраненных исходных файлов прайсов.</b>\n\n"
                    "Используйте команду <code>/fetch_fergana</code> для скачивания или <code>/collect_fergana</code> для полного сбора с каналов."
                )
                return
                
            file_ids = [f.id for f in input_files]
            file_names_str = ", ".join([f"<code>{f.filename}</code>" for f in input_files[:4]])
            more_str = f" и еще {len(input_files) - 4} файлов" if len(input_files) > 4 else ""
            
            task_record = TaskRecord(
                user_id=target_user.id,
                task_type="svodny_fergana",
                status="pending",
                is_automated=True,
                file_ids=file_ids,
                progress_message="Постановка задачи в очередь..."
            )
            db.add(task_record)
            db.commit()
            db.refresh(task_record)
            
            run_pipeline_task.delay(task_record.id)
            
            await message.reply(
                f"🍇 <b>Запущена быстрая сборка сводного прайса Ферганской долины!</b>\n\n"
                f"📁 <b>Файлы в обработке ({len(input_files)} шт.):</b>\n{file_names_str}{more_str}\n\n"
                f"⏱ <i>Формирую матрицу Долины (~30 сек)... Готовый результат будет отправлен сюда.</i>"
            )
            return
        except Exception as e:
            logger.exception(f"Error starting just_collect_fergana task: {e}")
            await message.reply("❌ Ошибка при запуске быстрой сборки сводного прайса Ферганской долины.")
            return
        finally:
            db.close()

    elif is_just_collect_republic:
        tg_user = message.from_user
        if not tg_user or tg_user.id not in settings.allowed_telegram_ids_set:
            logger.warning(f"User {tg_user.id if tg_user else 'unknown'} tried to trigger just_collect but is not allowed.")
            return
            
        user = get_or_create_user(telegram_id=tg_user.id)
        db = SessionLocal()
        try:
            target_user = user
            input_files = db.query(FileRecord).filter(
                FileRecord.user_id == target_user.id,
                FileRecord.file_type == "input",
                ~FileRecord.storage_path.like("%/fergana/%")
            ).all()
            
            if not input_files and target_user.id != 1:
                # Если у пользователя нет своих файлов, берем загруженные файлы системного пользователя 1
                input_files = db.query(FileRecord).filter(
                    FileRecord.user_id == 1,
                    FileRecord.file_type == "input",
                    ~FileRecord.storage_path.like("%/fergana/%")
                ).all()
                if input_files:
                    target_user = db.query(User).filter(User.id == 1).first() or target_user
            
            if not input_files:
                await message.reply(
                    "⚠️ <b>На сервере нет сохраненных исходных файлов прайсов.</b>\n\n"
                    "Используйте команду <code>/collect</code> для полного сбора с каналов или <code>/fetch</code> для скачивания."
                )
                return
                
            file_ids = [f.id for f in input_files]
            file_names_str = ", ".join([f"<code>{f.filename}</code>" for f in input_files[:4]])
            more_str = f" и еще {len(input_files) - 4} файлов" if len(input_files) > 4 else ""
            
            task_record = TaskRecord(
                user_id=target_user.id,
                task_type="svodny_horizontal",
                status="pending",
                is_automated=True,
                file_ids=file_ids,
                progress_message="Постановка задачи в очередь..."
            )
            db.add(task_record)
            db.commit()
            db.refresh(task_record)
            
            run_pipeline_task.delay(task_record.id)
            
            await message.reply(
                f"🚀 <b>Запущена быстрая сборка сводного прайса!</b>\n\n"
                f"📁 <b>Файлы в обработке ({len(input_files)} шт.):</b>\n{file_names_str}{more_str}\n\n"
                f"⏱ <i>Формирую отчет (~1 мин)... Готовый результат будет отправлен сюда.</i>"
            )
            return
        except Exception as e:
            logger.exception(f"Error starting just_collect task: {e}")
            await message.reply("❌ Ошибка при запуске быстрой сборки сводного прайса.")
            return
        finally:
            db.close()

    # 3. Проверяем команды скачивания и сбора прайсов через Scout
    is_fergana_fetch = (
        low_text.startswith(("/fetch_fergana", "/download_fergana")) or
        "скачай ферган" in low_text or
        "скачай прайсы ферган" in low_text
    )

    is_fergana_collect = (
        low_text.startswith(("/fergana", "/collect_fergana")) or
        ("ферган" in low_text and ("сбор" in low_text or "собрать" in low_text or "сводный" in low_text))
    )

    is_republic_fetch = (
        low_text.startswith(("/fetch", "/download_prices")) or
        "скачай прайсы" in low_text or
        "скачай последние прайсы" in low_text or
        "загрузи прайсы" in low_text
    )

    is_republic_collect = (
        low_text.startswith(("/collect", "/svodny")) or
        "сборщик" in low_text or
        "сборка" in low_text or
        "@lightprice_aggr_bot" in low_text or
        "агрегатор" in low_text
    )

    if not (is_fergana_fetch or is_fergana_collect or is_republic_fetch or is_republic_collect):
        return
        
    tg_user = message.from_user
    if not tg_user:
        return
        
    # Проверяем, входит ли отправитель в список разрешенных
    if tg_user.id not in settings.allowed_telegram_ids_set:
        logger.warning(f"User {tg_user.id} ({tg_user.full_name}) tried to trigger collection but is not allowed.")
        return
        
    if is_fergana_fetch:
        endpoint_path = "/fetch_fergana"
        start_msg = "🍇 <b>[ФЕРГАНСКАЯ ДОЛИНА]</b> Запрос на скачивание получен. Начинаю скачивать свежие прайсы 17 местных оптовиков в папку fergana/..."
    elif is_fergana_collect:
        endpoint_path = "/collect_fergana"
        start_msg = "🍇 <b>[ФЕРГАНСКАЯ ДОЛИНА]</b> Запрос на полный сбор получен. Начинаю опрос каналов 17 местных оптовиков и построение матрицы..."
    elif is_republic_fetch:
        endpoint_path = "/fetch"
        start_msg = "⏳ Запрос на скачивание прайс-листов получен. Начинаю скачивать свежие прайсы (100% / 25%) со всех каналов дистрибьюторов..."
    else:
        endpoint_path = "/collect"
        start_msg = "⏳ Запрос на сбор прайс-листов получен. Начинаю опрашивать каналы дистрибьюторов..."
        
    sent_msg = await message.answer(start_msg)
    
    # Отправляем POST запрос к Scout Agent
    try:
        import json
        url = f"http://scout_agent:8080{endpoint_path}"
        payload = json.dumps({
            "chat_id": message.chat.id,
            "message_id": sent_msg.message_id
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("X-Internal-API-Key", settings.INTERNAL_API_KEY)
        req.add_header("Content-Type", "application/json")
        
        loop = asyncio.get_running_loop()
        
        def _send_request():
            with urllib.request.urlopen(req, timeout=10.0) as response:
                status = response.status
                body = response.read().decode()
                return status, body
                
        status, body = await loop.run_in_executor(None, _send_request)
        if status == 200:
            logger.info(f"Successfully triggered Scout Agent endpoint {endpoint_path}.")
        else:
            logger.error(f"Failed to trigger Scout Agent. Status: {status}, Response: {body}")
            await message.answer("❌ Ошибка при взаимодействии с Агентом-Сборщиком (Scout Agent).")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTPError triggering Scout Agent: {e.code} - {e.reason}")
        await message.answer("❌ Ошибка при взаимодействии с Агентом-Сборщиком (Scout Agent).")
    except Exception as e:
        logger.exception(f"Exception while contacting Scout Agent: {e}")
        await message.answer(f"❌ Не удалось связаться с Агентом-Сборщиком: {str(e)}")




