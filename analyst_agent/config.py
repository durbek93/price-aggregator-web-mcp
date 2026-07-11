# -*- coding: utf-8 -*-
import os

ANALYST_BOT_TOKEN = os.getenv("ANALYST_BOT_TOKEN", "")
MAIN_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Extract Main Bot ID from its token (part before the colon)
MAIN_BOT_ID = None
if MAIN_BOT_TOKEN and ":" in MAIN_BOT_TOKEN:
    try:
        MAIN_BOT_ID = int(MAIN_BOT_TOKEN.split(":")[0])
    except ValueError:
        pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "internal_secret_api_key_98765")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# Telelgram group ID to limit bot listening
TELEGRAM_GROUP_ID_RAW = os.getenv("TELEGRAM_GROUP_ID", "")
TELEGRAM_GROUP_ID = None
if TELEGRAM_GROUP_ID_RAW:
    try:
        if TELEGRAM_GROUP_ID_RAW.startswith("-") and TELEGRAM_GROUP_ID_RAW[1:].isdigit():
            TELEGRAM_GROUP_ID = int(TELEGRAM_GROUP_ID_RAW)
        elif TELEGRAM_GROUP_ID_RAW.isdigit():
            TELEGRAM_GROUP_ID = int(TELEGRAM_GROUP_ID_RAW)
    except ValueError:
        pass
