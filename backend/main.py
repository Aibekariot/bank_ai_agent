"""
FastAPI backend для чата с AI-агентом банка.

Запуск:
    pip install -r requirements.txt
    export GEMINI_API_KEY=your_key_here
    uvicorn main:app --reload --port 8000
"""
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import run_chat

app = FastAPI(title="Eldik Bank AI Agent")

# Для демо разрешаем все origins. В проде сузить до конкретных доменов.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str  # "user" или "model"
    text: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.messages:
        raise HTTPException(status_code=400, detail="Сообщения не переданы")

    history = [{"role": m.role, "text": m.text} for m in request.messages]

    try:
        reply = run_chat(history)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(reply=reply)
