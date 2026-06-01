"""Load stable .env configuration."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(REPO_ROOT / ".env")

CRC_API_HOST = os.getenv("CRC_API_HOST", "https://api.crc.testing:6443")
EDA_WEBHOOK_URL = os.getenv("EDA_WEBHOOK_URL", "http://127.0.0.1:5000/endpoint")
EDA_WEBHOOK_TOKEN = os.getenv("EDA_WEBHOOK_TOKEN", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
STALE_DAYS = int(os.getenv("STALE_DAYS", "2"))
MIN_GAP_PCT = float(os.getenv("MIN_GAP_PCT", "20"))
MIN_SAVING_USD = float(os.getenv("MIN_SAVING_USD", "5"))
CPU_RATE = float(os.getenv("CPU_RATE", "0.03"))
MEM_GIB_RATE = float(os.getenv("MEM_GIB_RATE", "0.005"))
RH_CLIENT_ID = os.getenv("RH_CLIENT_ID", "")
RH_CLIENT_SECRET = os.getenv("RH_CLIENT_SECRET", "")
