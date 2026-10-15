# Eldik Bank AI Agent

Информационный ИИ-чат для клиентов Eldik Bank (физические лица): карты, кредиты,
вклады, переводы, банкоматы и отделения, курсы валют, калькуляторы.
Агент отвечает только по собранным данным банка и не имеет доступа к счетам клиентов.

- `lib/` - Flutter-клиент (экран чата).
- `backend/` - FastAPI-сервер: агент, фильтр тем, инструменты, база знаний в JSON.
- `jisonki_eldika/` - сырые данные с сайта, из них собирается `backend/knowledge/`.

## Запуск сервера (Windows)

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Ключи и настройки лежат в `backend/.env` (в Git не попадает):
`LLM_PROVIDER`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `GEMINI_API_KEY`, `DEV_LOG`.

## Запуск клиента

Адрес сервера задан в `lib/services/api_service.dart` (`baseUrl`), затем `flutter run`.

## Тесты

```
cd backend
set PYTHONUTF8=1
python tests\test_build_knowledge.py
python tests\test_tools.py
python tests\test_scope_guard.py
python tests\test_main.py
```

Ручная проверка ответов агента: `backend/tests/TEST_QUESTIONS.md`.
Подробности для разработки: `CLAUDE.md`.
