"""Basit dosya logu — emirdeck.log (proje klasörü)."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime


def _log_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "emirdeck.log")


def log(msg: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} {msg}"
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log_exc(prefix: str = "ERROR") -> None:
    log(f"{prefix}: {traceback.format_exc()}")
