from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


def get_admin_subs() -> set[str]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    values = config.get("admin_subs", []) if isinstance(config, dict) else []
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str) and value and not value.startswith("impersonate:")}
