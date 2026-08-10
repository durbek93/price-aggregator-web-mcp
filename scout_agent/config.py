# -*- coding: utf-8 -*-
import os

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_PASSWORD = os.getenv("TELEGRAM_PASSWORD", "")

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "internal_secret_api_key_98765")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# Comma-separated list of channel usernames or IDs to monitor
DISTRIBUTOR_CHANNELS_RAW = os.getenv("DISTRIBUTOR_CHANNELS", "")
DISTRIBUTOR_CHANNELS = []
if DISTRIBUTOR_CHANNELS_RAW:
    for x in DISTRIBUTOR_CHANNELS_RAW.split(","):
        val = x.strip()
        if not val:
            continue
        # If it's a numeric ID (starts with minus or is digits)
        if val.startswith("-") and val[1:].isdigit():
            DISTRIBUTOR_CHANNELS.append(int(val))
        elif val.isdigit():
            DISTRIBUTOR_CHANNELS.append(int(val))
        else:
            DISTRIBUTOR_CHANNELS.append(val)

# Configurations for on-demand bot requests
DEMAND_BOT_USERNAME = os.getenv("DEMAND_BOT_USERNAME", "")
DEMAND_BOT_TRIGGER_CRON = os.getenv("DEMAND_BOT_TRIGGER_CRON", "0 14 * * 0,2,3,5,6")  # Каждый день кроме Пн и Чт в 14:00 (Вт, Ср, Пт, Сб, Вс)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID", "")
