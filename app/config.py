from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOCX_TEMPLATES_DIR = BASE_DIR / "templates_docx"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
DB_PATH = Path(_env("DB_PATH", str(BASE_DIR / "data" / "dkp.db")))