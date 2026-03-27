"""Reference SQLite database shipped with the project."""

from __future__ import annotations

import os
from pathlib import Path

INSTANCE_DIR = Path(__file__).resolve().parent

# Canonical location (do not move without updating docs).
_DEFAULT_KOP_DATE_DB = INSTANCE_DIR / "Kop_Date.db"


def get_kop_date_db_path() -> Path:
    """Return path to Kop_Date.db.

    Override with env ``CALLIGRAPHY_DB_PATH`` or ``KOP_DATE_DB_PATH`` (absolute
    or relative to cwd) for tests or alternate copies.
    """
    for key in ("CALLIGRAPHY_DB_PATH", "KOP_DATE_DB_PATH"):
        raw = os.environ.get(key)
        if raw:
            return Path(raw).expanduser().resolve()
    return _DEFAULT_KOP_DATE_DB.resolve()


KOP_DATE_DB_PATH = _DEFAULT_KOP_DATE_DB

__all__ = [
    "INSTANCE_DIR",
    "KOP_DATE_DB_PATH",
    "get_kop_date_db_path",
]
