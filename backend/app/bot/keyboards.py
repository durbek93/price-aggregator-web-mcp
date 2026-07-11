# -*- coding: utf-8 -*-
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Возвращает главное клавиатурное меню действий."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Сводный прайс (гориз.)", callback_data="run:svodny_horizontal"),
        InlineKeyboardButton(text="📈 Сводный прайс (верт.)", callback_data="run:svodny_vertical")
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Анализ ассортимента", callback_data="run:assortment"),
        InlineKeyboardButton(text="💡 Подсветить дешевые", callback_data="run:cheapest")
    )
    builder.row(
        InlineKeyboardButton(text="🏢 Анализ лучших поставщиков", callback_data="run:best_suppliers")
    )
    builder.row(
        InlineKeyboardButton(text="🧹 Очистить мои файлы", callback_data="clear_files")
    )
    return builder.as_markup()
