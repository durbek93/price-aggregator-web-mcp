# -*- coding: utf-8 -*-
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Возвращает главное клавиатурное меню действий."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Сводный прайс (Республика)", callback_data="run:svodny_horizontal"),
        InlineKeyboardButton(text="🍇 Сводный (Ферганская долина)", callback_data="collect:fergana")
    )
    builder.row(
        InlineKeyboardButton(text="📈 Сводный прайс (верт.)", callback_data="run:svodny_vertical"),
        InlineKeyboardButton(text="🔍 Анализ ассортимента", callback_data="run:assortment")
    )
    builder.row(
        InlineKeyboardButton(text="💡 Подсветить дешевые", callback_data="run:cheapest"),
        InlineKeyboardButton(text="🏢 Анализ лучших поставщиков", callback_data="run:best_suppliers")
    )
    builder.row(
        InlineKeyboardButton(text="🧹 Очистить мои файлы", callback_data="clear_files")
    )
    return builder.as_markup()
