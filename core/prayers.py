import json
import os
import uuid

from core.paths import config_dir

PRAYERS_PATH = os.path.join(config_dir(), "prayers.json")


def load() -> list:
    if os.path.isfile(PRAYERS_PATH):
        try:
            with open(PRAYERS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save(items: list):
    os.makedirs(os.path.dirname(PRAYERS_PATH), exist_ok=True)
    with open(PRAYERS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def new_item(name: str, reason: str = "") -> dict:
    return {"id": uuid.uuid4().hex[:8], "name": name.strip(), "reason": reason.strip()}
