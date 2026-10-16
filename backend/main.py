"""
FastAPI backend для чата с AI-агентом банка.

Запуск (из папки backend):
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Контракт API для приложения: contract/README.md.
"""
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import time
from typing import Literal

import demo_bank_api
import dev_log
from agent import run_chat

app =FastAPI(title="Eldik Bank AI Agent")

# Имитация API банка для демо-приложения (к агенту не относится).
app.include_router(demo_bank_api.router)

# Для демо разрешаем все origins. В проде сузить до конкретных доменов.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    text: str


# Историю присылает клиент, поэтому сервер её ограничивает: длинный диалог
# замедляет и удорожает каждый запрос к модели.
MAX_HISTORY_MESSAGES = 20      # модели уходят только последние N сообщений
MAX_USER_MESSAGE_CHARS = 2000  # длиннее - отказ (вопрос клиента так не выглядит)
MAX_OLD_MESSAGE_CHARS = 3000   # старые сообщения обрезаются до этой длины


def prepare_history(messages: list[ChatMessage]) -> list[dict]:
    """Проверяет и обрезает историю. Ошибки - HTTPException с понятным текстом."""
    if not messages:
        raise HTTPException(status_code=400, detail="Сообщения не переданы")
    if messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="Последнее сообщение должно быть от пользователя")
    if len(messages[-1].text) > MAX_USER_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Сообщение слишком длинное. Сократите вопрос до {MAX_USER_MESSAGE_CHARS} символов.",
        )

    recent = messages[-MAX_HISTORY_MESSAGES:]
    # История для модели должна начинаться с вопроса пользователя.
    while recent and recent[0].role != "user":
        recent = recent[1:]

    return [
        {"role": m.role, "text": m.text if i == len(recent) - 1 else m.text[:MAX_OLD_MESSAGE_CHARS]}
        for i, m in enumerate(recent)
    ]


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    # Идентификатор диалога от приложения. Пока не хранится: хранение
    # диалога на сервере запланировано на стадию Pilot.
    session_id: str | None = Field(default=None, max_length=100)


class ChatAction(BaseModel):
    """Действие в приложении из каталога contract/actions.json (кнопка под ответом)."""

    name: str
    label: str
    params: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    actions: list[ChatAction] = Field(default_factory=list)


@app.get("/health")
def health():
    return {"status": "ok"}


# /chat оставлен для старых сборок приложения; новые вызывают /v1/chat.
@app.post("/v1/chat", response_model=ChatResponse)
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, authorization: str | None = Header(default=None)):
    history = prepare_history(request.messages)

    # Токен приложения пока не проверяется (в демо он вымышленный): проверка
    # у банка появится вместе с личными данными. Здесь только отметка в логе.
    print(f"[AUTH] токен: {'есть' if authorization else 'нет'}, session_id: {request.session_id or '-'}")

    # Запись диалога в logs/dialogs.txt (только если в .env DEV_LOG=1).
    dev_log.start_request()
    started = time.perf_counter()

    try:
        result = run_chat(history)
    except Exception as exc:  # noqa: BLE001
        dev_log.record(history, "", time.perf_counter() - started, error=str(exc))
        print(f"[ERROR] {type(exc).__name__}: {exc}")  # подробности только в логе сервера

        # Клиенту отдаём короткое безопасное сообщение, без внутренних деталей.
        if "429" in str(exc):
            raise HTTPException(
                status_code=503,
                detail="Сервис сейчас перегружен. Повторите вопрос через минуту.",
            ) from exc
        raise HTTPException(
            status_code=500,
            detail="Не удалось получить ответ. Попробуйте ещё раз.",
        ) from exc

    dev_log.record(
        history, result.reply, time.perf_counter() - started,
        actions=[a["name"] for a in result.actions],
    )
    return ChatResponse(reply=result.reply, actions=result.actions)
