# -*- coding: utf-8 -*-
import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, html, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, Message, CallbackQuery
from aiogram.filters import Command

import config
from auditor import audit_svodny_price, find_latest_svodny, AuditReport
from healer import diagnose_and_propose_fix, ProposedFix
from api_client import save_distributor_rule, trigger_rerun_pipeline, wait_for_task_completion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("debugger_agent")

bot = Bot(token=config.DEBUGGER_BOT_TOKEN) if config.DEBUGGER_BOT_TOKEN else None
dp = Dispatcher()

app = FastAPI(title="Debugger Agent Service")

# In-memory store for active proposed fixes waiting for confirmation
ACTIVE_FIXES: Dict[str, ProposedFix] = {}


class FixActionRequest(BaseModel):
    fix_id: str
    chat_id: Optional[int] = None


def get_fix_keyboard(fix_id: str) -> InlineKeyboardMarkup:
    """Builds inline confirmation keyboard."""
    kb = [
        [
            InlineKeyboardButton(text="✅ Применить и пересобрать", callback_data=f"apply_fix:{fix_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_fix:{fix_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def send_discrepancy_alert(fix: ProposedFix, target_chat_id: int) -> None:
    """Sends detailed discrepancy notification with interactive inline buttons."""
    if not bot:
        return

    text = (
        f"🛠 <b>[Агент-Отладчик] Обнаружена ошибка в сводном прайсе!</b>\n\n"
        f"🏢 <b>Дистрибьютор:</b> {html.bold(fix.distributor_label)}\n"
        f"📁 <b>Файл:</b> <code>{html.quote(fix.raw_filename)}</code>\n\n"
        f"⚠️ <b>Проблема:</b>\n{html.quote(fix.issue_summary)}\n\n"
        f"🔍 <b>Причина:</b>\n{html.quote(fix.root_cause)}\n\n"
        f"💡 <b>Предлагаемое решение:</b>\n{html.quote(fix.explanation)}\n"
        f"• Колонка 25%: <code>{fix.proposed_rule.get('p25_col', 'Цена')}</code>\n"
        f"• Колонка 100%: <code>{fix.proposed_rule.get('p100_col', 'Цена')}</code>\n\n"
        f"<i>Применить это правило и пересобрать сводный прайс?</i>"
    )

    try:
        await bot.send_message(
            chat_id=target_chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=get_fix_keyboard(fix.fix_id)
        )
        logger.info(f"Discrepancy alert sent to {target_chat_id} for fix {fix.fix_id}")
    except Exception as ex:
        logger.error(f"Failed to send discrepancy alert to {target_chat_id}: {ex}")


async def perform_full_audit(target_chat_id: Optional[int] = None) -> AuditReport:
    """Runs full audit and triggers healing diagnosis if discrepancies are found."""
    latest_svodny = find_latest_svodny(config.OUTPUT_DIR)
    chat_id = target_chat_id or config.TELEGRAM_GROUP_ID or (config.ALLOWED_TELEGRAM_IDS[0] if config.ALLOWED_TELEGRAM_IDS else None)

    if not latest_svodny:
        logger.warning("No svodny price file found to audit.")
        if chat_id and bot:
            try:
                await bot.send_message(chat_id, "ℹ️ Файлы сводного прайса не найдены для аудита.")
            except Exception:
                pass
        return AuditReport(svodny_filepath=Path(), is_valid=False, summary_text="Файлы не найдены")

    logger.info(f"Auditing svodny file: {latest_svodny.name}")
    report = audit_svodny_price(latest_svodny, config.UPLOAD_DIR)

    if report.is_valid:
        logger.info(report.summary_text)
        if chat_id and bot:
            try:
                await bot.send_message(chat_id, report.summary_text)
            except Exception:
                pass
        return report

    logger.warning(f"Audit found {len(report.discrepancies)} discrepancies! Initiating healing...")

    for disc in report.discrepancies:
        fix = await diagnose_and_propose_fix(disc)
        ACTIVE_FIXES[fix.fix_id] = fix
        if chat_id:
            await send_discrepancy_alert(fix, chat_id)

    return report


def is_authorized(user_id: int, chat_id: Optional[int] = None) -> bool:
    """Checks whether the user or chat is authorized to perform auditor actions."""
    if not config.ALLOWED_TELEGRAM_IDS and not config.TELEGRAM_GROUP_ID:
        return True
    if config.ALLOWED_TELEGRAM_IDS and user_id in config.ALLOWED_TELEGRAM_IDS:
        return True
    if config.TELEGRAM_GROUP_ID and chat_id == config.TELEGRAM_GROUP_ID:
        return True
    return False


def verify_internal_key(x_internal_key: Optional[str]) -> None:
    """Strictly validates the internal secret key."""
    if not config.INTERNAL_API_KEY:
        return
    if not x_internal_key or x_internal_key != config.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid or missing X-Internal-Key"
        )


# --- Telegram Bot Handlers (Auditor Bot @lightyak_auditor_bot) ---

@dp.message(Command("start"))
@dp.message(Command("help"))
async def bot_start_handler(message: Message):
    if not is_authorized(message.from_user.id if message.from_user else 0, message.chat.id):
        await message.answer("⛔ У вас нет доступа к управлению Агентом-Аудитором.")
        return

    await message.answer(
        "👋 Привет! Я <b>Агент-Отладчик и Аудитор</b> (@lightyak_auditor_bot).\n\n"
        "🔎 <b>Мои возможности:</b>\n"
        "• <code>/audit</code> или <code>/debug</code> — провести полный аудит свежего сводного прайса по препаратам Материа Медика;\n"
        "• <code>/status</code> — статус агента-отладчика;\n"
        "• Автоматическая диагностика расхождений колонок и самоисправление с генерацией правил.",
        parse_mode="HTML"
    )


@dp.message(Command("audit"))
@dp.message(Command("debug"))
async def bot_audit_command(message: Message):
    if not is_authorized(message.from_user.id if message.from_user else 0, message.chat.id):
        await message.answer("⛔ У вас нет прав для запуска аудита.")
        return

    await message.answer("🔎 <b>Запускаю аудит сводного прайса по препаратам Материя Медика...</b>", parse_mode="HTML")
    await perform_full_audit(target_chat_id=message.chat.id)


@dp.message(Command("status"))
async def bot_status_command(message: Message):
    if not is_authorized(message.from_user.id if message.from_user else 0, message.chat.id):
        await message.answer("⛔ У вас нет прав для просмотра статуса.")
        return

    latest_svodny = find_latest_svodny(config.OUTPUT_DIR)
    sv_text = latest_svodny.name if latest_svodny else "нет файлов"
    await message.answer(
        f"🤖 <b>Статус Агента-Аудитора:</b>\n"
        f"• Сервис: <code>активен</code>\n"
        f"• Активных предложений по правкам: <code>{len(ACTIVE_FIXES)}</code>\n"
        f"• Последний сводный: <code>{sv_text}</code>",
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("apply_fix:"))
async def callback_apply_fix_handler(callback: CallbackQuery):
    if not is_authorized(callback.from_user.id if callback.from_user else 0, callback.message.chat.id if callback.message else None):
        await callback.answer("⛔ Недостаточно прав для применения исправления!", show_alert=True)
        return

    fix_id = callback.data.split(":", 1)[1]
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Применяю исправление...")
    req = FixActionRequest(fix_id=fix_id, chat_id=callback.message.chat.id if callback.message else None)
    await execute_apply_fix(req)


@dp.callback_query(F.data.startswith("reject_fix:"))
async def callback_reject_fix_handler(callback: CallbackQuery):
    if not is_authorized(callback.from_user.id if callback.from_user else 0, callback.message.chat.id if callback.message else None):
        await callback.answer("⛔ Недостаточно прав для отклонения исправления!", show_alert=True)
        return

    fix_id = callback.data.split(":", 1)[1]
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Исправление отклонено.")
    req = FixActionRequest(fix_id=fix_id, chat_id=callback.message.chat.id if callback.message else None)
    await execute_reject_fix(req)


# --- Core Fix Execution Logic ---

async def execute_apply_fix(req: FixActionRequest) -> Dict[str, Any]:
    """Applies the fix, updates distributor rules, and re-runs the pipeline."""
    fix = ACTIVE_FIXES.get(req.fix_id)
    if not fix:
        raise HTTPException(status_code=404, detail="Fix not found or expired")

    chat_id = req.chat_id or config.TELEGRAM_GROUP_ID or (config.ALLOWED_TELEGRAM_IDS[0] if config.ALLOWED_TELEGRAM_IDS else None)

    if chat_id and bot:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⏳ <b>Применяю правило для {fix.distributor_label}...</b>\nЗапускаю пересборку сводного прайса...",
                parse_mode="HTML"
            )
        except Exception:
            pass

    # 1. Save rule
    save_distributor_rule(fix.distributor_key, fix.proposed_rule)

    # 2. Trigger pipeline re-run
    task_id = await trigger_rerun_pipeline()
    if not task_id:
        if chat_id and bot:
            await bot.send_message(chat_id, "❌ Ошибка при запуске задачи пересборки в бэкенде.")
        return {"status": "error", "message": "Failed to trigger backend pipeline"}

    # 3. Wait for completion
    success = await wait_for_task_completion(task_id, timeout_sec=180)
    if not success:
        if chat_id and bot:
            await bot.send_message(chat_id, "❌ Ошибка: пересборка завершилась сбоем.")
        return {"status": "error", "message": "Pipeline execution failed"}

    # 4. Re-audit and send updated file
    latest_svodny = find_latest_svodny(config.OUTPUT_DIR)
    if latest_svodny and latest_svodny.exists() and chat_id and bot:
        new_report = audit_svodny_price(latest_svodny, config.UPLOAD_DIR)
        doc = FSInputFile(str(latest_svodny))
        status_line = "✅ <b>Все препараты Материя Медика проверены, ошибок нет!</b>" if new_report.is_valid else "⚠️ Пересборка завершена, но остаются замечания."
        
        try:
            await bot.send_document(
                chat_id=chat_id,
                document=doc,
                caption=(
                    f"🎉 <b>Сводный прайс успешно пересобран и обновлен!</b>\n\n"
                    f"Правило для <b>{fix.distributor_label}</b> сохранено:\n"
                    f"• Базовая 25%: <code>{fix.proposed_rule.get('p25_col')}</code>\n"
                    f"• Со скидкой 100%: <code>{fix.proposed_rule.get('p100_col')}</code>\n\n"
                    f"{status_line}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error sending document to {chat_id}: {e}")

    ACTIVE_FIXES.pop(req.fix_id, None)
    return {"status": "ok", "message": "Fix applied and pipeline re-run successfully"}


async def execute_reject_fix(req: FixActionRequest) -> Dict[str, Any]:
    """Rejects the proposed fix."""
    ACTIVE_FIXES.pop(req.fix_id, None)
    chat_id = req.chat_id or config.TELEGRAM_GROUP_ID or (config.ALLOWED_TELEGRAM_IDS[0] if config.ALLOWED_TELEGRAM_IDS else None)
    if chat_id and bot:
        try:
            await bot.send_message(chat_id, "❌ Исправление отклонено. Правило не сохранено.")
        except Exception:
            pass
    return {"status": "ok", "message": "Fix rejected"}


# --- FastAPI Webhook Endpoints ---

@app.post("/audit")
async def api_trigger_audit(
    background_tasks: BackgroundTasks,
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key")
):
    """Webhook triggered after a svodny task finishes."""
    verify_internal_key(x_internal_key)
    background_tasks.add_task(perform_full_audit)
    return {"status": "ok", "message": "Audit started in background"}


@app.post("/apply_fix")
async def api_apply_fix(
    req: FixActionRequest,
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key")
):
    """Applies the fix, updates distributor rules, and re-runs the pipeline via API."""
    verify_internal_key(x_internal_key)
    return await execute_apply_fix(req)


@app.post("/reject_fix")
async def api_reject_fix(
    req: FixActionRequest,
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key")
):
    """Rejects the proposed fix via API."""
    verify_internal_key(x_internal_key)
    return await execute_reject_fix(req)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "debugger_agent", "active_fixes_count": len(ACTIVE_FIXES)}


async def main():
    server_config = uvicorn.Config(app, host="0.0.0.0", port=8001, log_level="info")
    server = uvicorn.Server(server_config)

    tasks = [server.serve()]
    if bot:
        logger.info("Starting Telegram Bot Polling for Auditor Bot (@lightyak_auditor_bot)...")
        tasks.append(dp.start_polling(bot))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())


