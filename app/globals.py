"""Constantes globales de configuration de ZenHome."""

import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
ZENHOME_ENV = os.getenv("ZENHOME_ENV", "production").lower()
DATA_DIR = Path(os.getenv("ZENHOME_DATA_DIR", PROJECT_DIR / "data"))
DATABASE_PATH = DATA_DIR / "zenhome.sqlite3"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
DAEMON_INTERVAL_SECONDS = int(os.getenv("ZENHOME_DAEMON_INTERVAL_SECONDS", "60"))
OCCURRENCES_HORIZON_DAYS = 730
HOME_URL = os.getenv("HOME_URL", "http://localhost:8000").rstrip("/")
NTFY_TOPIC_PREFIX = os.getenv("ZENHOME_NTFY_TOPIC_PREFIX", "ZenHome")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOKEN = os.getenv("NTFY_TOKEN") or None
NTFY_USER = os.getenv("NTFY_USER") or None
NTFY_PASSWORD = os.getenv("NTFY_PASSWORD") or None
