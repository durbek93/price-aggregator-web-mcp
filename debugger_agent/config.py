# -*- coding: utf-8 -*-
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEBUGGER_BOT_TOKEN = os.getenv("DEBUGGER_BOT_TOKEN", "")
TELEGRAM_BOT_TOKEN = DEBUGGER_BOT_TOKEN


ALLOWED_TELEGRAM_IDS_RAW = os.getenv("ALLOWED_TELEGRAM_IDS", "")
ALLOWED_TELEGRAM_IDS = []
if ALLOWED_TELEGRAM_IDS_RAW:
    for x in ALLOWED_TELEGRAM_IDS_RAW.split(","):
        val = x.strip()
        if val.isdigit():
            ALLOWED_TELEGRAM_IDS.append(int(val))
        elif val.startswith("-") and val[1:].isdigit():
            ALLOWED_TELEGRAM_IDS.append(int(val))

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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "11121993_29081966")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/data/uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/data/outputs"))
RULES_FILE = Path(os.getenv("RULES_FILE", "/app/data/distributor_rules.json"))
