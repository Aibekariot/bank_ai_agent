"""
dev_log.py - запись диалогов в читаемый текстовый файл для тестирования.

Зачем: чтобы не копировать ответы агента из приложения вручную. Включаете
запись, задаёте вопросы в приложении, потом открываете один файл
backend/logs/dialogs.txt (или присылаете его целиком для разбора).

В файл попадает: время, вопрос, ответ, какие инструменты вызвала модель,
сколько секунд заняло, сколько сообщений было в истории.

Включение (в backend/.env):
    DEV_LOG=1

По умолчанию запись ВЫКЛЮЧЕНА. Не включайте её на сервере с реальными
клиентами: в файле лежат тексты вопросов, а вопросы могут содержать
личные данные. Папка logs/ должна быть в .gitignore.
"""

from __future__ import annotations

import contextvars
import os
import threading
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "dialogs.txt"

_tools: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "dev_log_tools", default=None
)
_write_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("DEV_LOG", "").strip().lower() in ("1", "true", "yes", "on")


def start_request() -> None:
    """Вызывается в начале обработки запроса: обнуляет список инструментов."""
    _tools.set([])


def note_tool(name: str) -> None:
    """Вызывается из agent.py при каждом вызове инструмента."""
    collected = _tools.get()
    if collected is not None:
        collected.append(name)


def record(history: list[dict], reply: str, elapsed: float, error: str | None = None) -> None:
    """Дописывает один обмен вопрос-ответ в logs/dialogs.txt."""
    if not enabled():
        return

    question = ""
    for message in reversed(history):
        if message.get("role") == "user":
            question = message.get("text", "")
            break

    tools = _tools.get() or []
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"=== {stamp} | {elapsed:.1f} с | "
        f"сообщений в истории: {len(history)} | "
        f"инструменты: {', '.join(tools) if tools else 'нет'} ==="
    )

    lines = [header, f"Вопрос: {question}", ""]
    if error:
        lines.append(f"ОШИБКА: {error}")
    else:
        lines.append(f"Ответ: {reply}")
    lines.extend(["", ""])

    try:
        with _write_lock:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
    except OSError as exc:
        # Запись логов не должна ломать ответ клиенту.
        print(f"[DEV_LOG] не удалось записать лог: {exc}")
