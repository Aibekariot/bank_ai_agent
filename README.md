# Eldik Bank AI Agent

ИИ-ассистент для клиентов Eldik Bank (физические лица): карты, кредиты, вклады,
переводы, банкоматы и отделения, курсы валют, калькуляторы. Ассистент отвечает только
по собранным данным банка и не имеет доступа к счетам клиентов. Он может предложить
действие в приложении (кнопку под ответом), но никогда не выполняет операции сам.

- `backend/` - FastAPI-сервер: агент, фильтр тем, инструменты, база знаний в JSON.
- `packages/eldik_assistant/` - модуль чата для встраивания в приложение банка.
- `lib/` - демо-банк: тестовое приложение с вымышленными данными, на котором
  проверяются действия ассистента.
- `contract/` - контракт ассистента с приложением: запрос, ответ, каталог действий.
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

## Запуск демо-банка

```
flutter run --dart-define=API_BASE_URL=http://<IP компьютера с сервером>:8000
```

Для эмулятора Android адрес компьютера `http://10.0.2.2:8000`. Вход: PIN `1234`.
Все счета, карты и переводы вымышленные, на экранах метка «ДЕМО».

## Тесты

```
cd backend
set PYTHONUTF8=1
python tests\test_build_knowledge.py
python tests\test_tools.py
python tests\test_scope_guard.py
python tests\test_main.py
python tests\test_actions.py
```

Flutter: `flutter analyze` и `flutter test` в корне и в `packages/eldik_assistant`.
С живым сервером (по желанию, тратит запросы к модели):
`flutter test test/live_server_test.dart --dart-define=LIVE_API=http://127.0.0.1:8000`.

Ручная проверка ответов агента: `backend/tests/TEST_QUESTIONS.md`.
Подробности для разработки: `CLAUDE.md`.
