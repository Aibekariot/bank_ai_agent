"""
Действия в приложении банка: проверка по каталогу contract/actions.json.

Агент не открывает экраны и не проводит операции сам. Инструменты прикладывают
к своему результату подсказку `_app_actions` (например, после курса валют -
"открыть курсы валют"), агент убирает её из ответа модели и пропускает
каждое действие через validate(). Приложение получает только действия из
каталога с проверенными параметрами и показывает их кнопками под ответом.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(
    os.environ.get(
        "ACTIONS_CATALOG",
        Path(__file__).resolve().parents[1] / "contract" / "actions.json",
    )
)

MAX_ACTIONS = 3  # больше кнопок под одним ответом только мешает клиенту

# Ключ, под которым инструменты отдают подсказки действий (модели не показывается).
HINT_KEY = "_app_actions"


@lru_cache(maxsize=1)
def catalog() -> dict:
    """Каталог действий: {имя: описание}."""
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return data["actions"]


def _clean_param(name: str, value, spec: dict):
    """Проверенное значение параметра или None, если оно не подходит."""
    if spec.get("type") == "string":
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or len(value) > spec.get("max_length", 200):
            return None
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            return None
        if "enum" in spec and value not in spec["enum"]:
            return None
        return value

    if spec.get("type") == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if "min" in spec and value < spec["min"]:
            return None
        if "max" in spec and value > spec["max"]:
            return None
        return int(value) if float(value).is_integer() else round(float(value), 2)

    return None


def validate(name: str, params: dict | None = None) -> dict | None:
    """
    Действие для приложения {"name", "label", "params"} или None.

    Неизвестное действие или неверный обязательный параметр - None.
    Неверный необязательный параметр просто отбрасывается.
    """
    spec = catalog().get(name)
    if spec is None:
        print(f"[ACTIONS] неизвестное действие отклонено: {name}")
        return None

    cleaned: dict = {}
    for key, value in (params or {}).items():
        param_spec = spec["params"].get(key)
        if param_spec is None:
            print(f"[ACTIONS] {name}: лишний параметр {key} отброшен")
            continue
        clean = _clean_param(key, value, param_spec)
        if clean is None:
            print(f"[ACTIONS] {name}: неверный параметр {key} отброшен")
            continue
        cleaned[key] = clean

    for key, param_spec in spec["params"].items():
        if param_spec.get("required") and key not in cleaned:
            print(f"[ACTIONS] {name}: нет обязательного параметра {key}, действие отклонено")
            return None

    label = spec["label"]
    label_param = spec.get("label_param")
    if label_param and cleaned.get(label_param):
        label = f"{label}: {cleaned[label_param]}"

    return {"name": name, "label": label, "params": cleaned}


def take_hints(tool_result) -> list[dict]:
    """Забирает подсказки действий из результата инструмента (результат меняется)."""
    if not isinstance(tool_result, dict):
        return []
    hints = tool_result.pop(HINT_KEY, None)
    return hints if isinstance(hints, list) else []


def add_unique(collected: list[dict], action: dict) -> bool:
    """Добавляет действие без повторов и не больше MAX_ACTIONS. True - добавлено."""
    key = (action["name"], json.dumps(action["params"], sort_keys=True, ensure_ascii=False))
    for existing in collected:
        if (existing["name"], json.dumps(existing["params"], sort_keys=True, ensure_ascii=False)) == key:
            return False
    if len(collected) >= MAX_ACTIONS:
        return False
    collected.append(action)
    return True


# ---------------------------------------------------------------------------
# Номер телефона для перевода
# ---------------------------------------------------------------------------

def normalize_kg_phone(raw: str | None) -> str | None:
    """
    Мобильный номер Кыргызстана в виде +996XXXXXXXXX или None.

    Принимает 0555 123 456, 555123456, 996555123456, +996 (555) 12-34-56.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("996"):
        digits = digits[3:]
    elif len(digits) == 10 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 9:
        return None
    return f"+996{digits}"
