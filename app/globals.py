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
