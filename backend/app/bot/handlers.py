# -*- coding: utf-8 -*-
import logging
import os
import urllib.request
import urllib.error
import asyncio
from datetime import datetime
from pathlib import Path

from aiogram import Router, Bot, F, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord, TaskRecord
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
        f"_(Действительна 7 дней)_",
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


@router.message(F.text)
async def handle_bot_mention_in_group(message: Message) -> None:
    """Обрабатывает упоминание бота-репортера в группе от разрешенных администраторов."""
    text = message.text or ""
    is_trigger = (
        "@lightprice_aggr_bot" in text.lower() or 
        "агрегатор" in text.lower() or 
        "сборщик" in text.lower() or 
        "сборка" in text.lower() or 
        text.strip().lower().startswith(("/collect", "/collect@lightprice_aggr_bot"))
    )
    if not is_trigger:
        return
        
    tg_user = message.from_user
    if not tg_user:
        return
        
    # Проверяем, входит ли отправитель в список разрешенных
    if tg_user.id not in settings.allowed_telegram_ids_set:
        logger.warning(f"User {tg_user.id} ({tg_user.full_name}) tried to trigger collection but is not allowed.")
        return
        
    logger.info(f"User {tg_user.id} triggered collection via bot mention.")
    await message.reply("⏳ Запрос на сбор прайс-листов получен. Начинаю опрашивать каналы дистрибьюторов...")
    
    # Отправляем POST запрос к Scout Agent для сбора прайсов
    try:
        url = "http://scout_agent:8080/collect"
        req = urllib.request.Request(url, method="POST")
        req.add_header("X-Internal-API-Key", settings.INTERNAL_API_KEY)
        
        loop = asyncio.get_running_loop()
        
        def _send_request():
            with urllib.request.urlopen(req, timeout=10.0) as response:
                status = response.status
                body = response.read().decode()
                return status, body
                
        status, body = await loop.run_in_executor(None, _send_request)
        if status == 200:
            logger.info("Successfully triggered Scout Agent for on-demand collection.")
        else:
            logger.error(f"Failed to trigger Scout Agent. Status: {status}, Response: {body}")
            await message.reply("❌ Ошибка при взаимодействии с Агентом-Сборщиком (Scout Agent).")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTPError triggering Scout Agent: {e.code} - {e.reason}")
        await message.reply("❌ Ошибка при взаимодействии с Агентом-Сборщиком (Scout Agent).")
    except Exception as e:
        logger.exception(f"Exception while contacting Scout Agent: {e}")
        await message.reply(f"❌ Не удалось связаться с Агентом-Сборщиком: {str(e)}")


