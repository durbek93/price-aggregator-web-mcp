# -*- coding: utf-8 -*-
"""Конфигурация каналов и групп оптовиков Ферганской долины."""

FERGANA_CHANNELS_CONFIG = [
    {"name": "Верона", "channel_id": -1001489759100},
    {"name": "Эверест", "channel_id": -1001321934769},
    {"name": "Мемори", "channel_id": -1001323609903},
    {"name": "Гейт", "channel_id": -1001349749017},
    {"name": "Аззам", "channel_id": -1001667950742},
    {"name": "Саида", "channel_id": -1001335864004},
    {"name": "Хожи Акбар", "channel_id": -1003895365538},
    {"name": "Акмал Фарм", "channel_id": -1001111861750},
    {"name": "Зилол мед", "channel_id": -1003250938697},
    {"name": "Фармакосмос", "channel_id": -1001793659418},
    {"name": "Турон", "channel_id": -1001182833604},
    {"name": "Макро", "channel_id": -1001099180331},
    {"name": "Охотник", "channel_id": -1001330861056},
    {"name": "Гармония", "channel_id": -1002588102223},
    {"name": "Рефлекс", "channel_id": -1001275091780},
    {"name": "Саховат", "channel_id": -1001275773396},
    {"name": "Саидмед Фарм", "channel_id": -1003922447234},
]

# Список ID для итерации
FERGANA_CHANNEL_IDS = [item["channel_id"] for item in FERGANA_CHANNELS_CONFIG]

# Словарь ID -> имя оптовика
FERGANA_NAME_BY_ID = {item["channel_id"]: item["name"] for item in FERGANA_CHANNELS_CONFIG}
