"""JSON tabanlı makro konfigürasyon yönetimi."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "language": "auto",
    "macros": [],
}


def _app_dir() -> str:
    import sys

    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_app_dir(), "config.json")


def ensure_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    if not os.path.isfile(path):
        save_config(deepcopy(DEFAULT_CONFIG), path)
        return deepcopy(DEFAULT_CONFIG)
    return load_config(path)


def load_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = deepcopy(DEFAULT_CONFIG)

    if not isinstance(data, dict):
        data = deepcopy(DEFAULT_CONFIG)

    language = str(data.get("language", "auto")).strip().lower() or "auto"
    if language not in ("auto", "en", "de", "tr", "zh"):
        language = "auto"

    macros = data.get("macros")
    if not isinstance(macros, list):
        macros = []

    cleaned: list[dict[str, Any]] = []
    for item in macros:
        if not isinstance(item, dict):
            continue
        trigger = str(item.get("trigger_key", "")).strip().lower()
        video = str(item.get("video_path", "")).strip()
        if not trigger or not video:
            continue
        cleaned.append(
            {
                "trigger_key": trigger,
                "video_path": video,
                "loop": bool(item.get("loop", False)),
            }
        )

    return {"language": language, "macros": cleaned}


def save_config(config: dict[str, Any], path: str = CONFIG_PATH) -> None:
    language = str(config.get("language", "auto")).strip().lower() or "auto"
    if language not in ("auto", "en", "de", "tr", "zh"):
        language = "auto"

    payload = {
        "language": language,
        "macros": [
            {
                "trigger_key": str(m.get("trigger_key", "")).strip().lower(),
                "video_path": str(m.get("video_path", "")).strip(),
                "loop": bool(m.get("loop", False)),
            }
            for m in config.get("macros", [])
            if isinstance(m, dict)
            and str(m.get("trigger_key", "")).strip()
            and str(m.get("video_path", "")).strip()
        ],
    }

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".config_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def find_macro_by_key(config: dict[str, Any], trigger_key: str) -> dict[str, Any] | None:
    key = trigger_key.strip().lower()
    for macro in config.get("macros", []):
        if macro.get("trigger_key") == key:
            return macro
    return None
