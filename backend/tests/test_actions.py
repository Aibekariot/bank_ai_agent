"""
Тесты действий в приложении: каталог contract/actions.json, проверка
параметров, подсказки инструментов и сбор действий в цикле агента.

Запуск (из папки backend):
    python tests/test_actions.py

Модель, интернет и ключи не нужны: вместо модели подставляется заглушка,
курсы валют подменяются.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import actions  # noqa: E402
import agent  # noqa: E402
import eldik_client  # noqa: E402
import tools  # noqa: E402
from llm.base import LLMProvider, LLMResponse, ToolCall  # noqa: E402

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


def hint_names(result):
    return [h["name"] for h in result.get(actions.HINT_KEY, [])]


# --- каталог -----------------------------------------------------------------

catalog = actions.catalog()
check("каталог содержит 5 действий", len(catalog) == 5)
for name, spec in catalog.items():
    action = actions.validate(name, spec["example"])
    check(f"пример из каталога проходит проверку: {name}",
          action is not None and action["params"] == spec["example"])

check("неизвестное действие отклоняется", actions.validate("make_payment", {}) is None)
check("нет обязательного параметра - действие отклоняется",
      actions.validate("open_card_product", {"title": "Visa Gold"}) is None)

a = actions.validate("open_exchange_rates", {"currency": "usd"})
check("неверный необязательный параметр отбрасывается, действие остаётся",
      a is not None and a["params"] == {})
a = actions.validate("open_exchange_rates", {"currency": "USD", "debug": True})
check("лишний параметр отбрасывается", a is not None and a["params"] == {"currency": "USD"})
check("подпись кнопки с параметром", a["label"] == "Курсы валют: USD")
check("подпись кнопки без параметра",
      actions.validate("open_pin_change", {})["label"] == "Сменить PIN-код")
a = actions.validate("open_locations", {"city": "Ош", "kind": "teleport"})
check("значение не из списка отбрасывается", a["params"] == {"city": "Ош"})

t = actions.validate("open_transfer_by_phone", {"phone": "+996555123456", "amount": True})
check("bool не считается суммой", t is not None and "amount" not in t["params"])
t = actions.validate("open_transfer_by_phone", {"amount": 0.5})
check("сумма меньше минимума отбрасывается", "amount" not in t["params"])
t = actions.validate("open_transfer_by_phone", {"amount": 500.0})
check("целая сумма приводится к int", t["params"]["amount"] == 500 and isinstance(t["params"]["amount"], int))
t = actions.validate("open_transfer_by_phone", {"phone": "0555123456"})
check("номер не в формате +996 отбрасывается", "phone" not in t["params"])

collected = []
x = actions.validate("open_pin_change", {})
check("add_unique добавляет новое действие", actions.add_unique(collected, x))
check("add_unique не добавляет повтор", not actions.add_unique(collected, dict(x)))
for city in ("Ош", "Нарын", "Талас"):
    actions.add_unique(collected, actions.validate("open_locations", {"city": city}))
check("не больше MAX_ACTIONS действий", len(collected) == actions.MAX_ACTIONS)

# --- номер телефона ------------------------------------------------------------

for raw, expected in [
    ("0555 123 456", "+996555123456"),
    ("+996 (555) 12-34-56", "+996555123456"),
    ("996700112233", "+996700112233"),
    ("555123456", "+996555123456"),
    ("12345", None),
    ("+7 999 123 45 67", None),
    ("", None),
]:
    check(f"номер {raw!r} -> {expected}", actions.normalize_kg_phone(raw) == expected)

# --- черновик перевода --------------------------------------------------------

r = tools.prepare_transfer(phone="0555 123 456", amount=500)
check("перевод: черновик готов", r["status"] == "draft_ready")
check("перевод: подсказка открыть форму с номером и суммой",
      r[actions.HINT_KEY] == [{"name": "open_transfer_by_phone",
                               "params": {"currency": "KGS", "phone": "+996555123456", "amount": 500}}])
check("перевод: модели сказано, что перевод НЕ выполнен", "НЕ выполнен" in r["note"])

r = tools.prepare_transfer(amount="1 500,50")
check("перевод: сумма строкой с пробелом и запятой", r.get("amount") == 1500.5)
check("перевод без номера: форма откроется, номер введёт клиент",
      r["status"] == "draft_ready" and "Номер получателя не указан" in r["note"])
r = tools.prepare_transfer(phone="12345", amount=500)
check("перевод: неверный номер - черновика нет", r["status"] == "need_phone" and actions.HINT_KEY not in r)
r = tools.prepare_transfer(phone="0555123456", amount=0)
check("перевод: нулевая сумма - черновика нет", r["status"] == "need_amount" and actions.HINT_KEY not in r)
r = tools.prepare_transfer(phone="0555123456", amount=100, currency="USD")
check("перевод: валюта кроме сома не готовится", r["status"] == "unsupported_currency")
r = tools.prepare_transfer(phone="0555123456", amount=100, currency="сом")
check("перевод: 'сом' понимается как KGS", r["status"] == "draft_ready")
check("перевод: подсказка проходит проверку каталога",
      actions.validate("open_transfer_by_phone",
                       tools.prepare_transfer("0555123456", 500)[actions.HINT_KEY][0]["params"]) is not None)

# --- подсказки инструментов ------------------------------------------------------

r = tools.find_locations("Ош")
check("точки в Оше: подсказка открыть список",
      r[actions.HINT_KEY] == [{"name": "open_locations", "params": {"city": "Ош"}}])
r = tools.find_locations("Атлантида")
check("точек не найдено: подсказки нет", actions.HINT_KEY not in r)

r = tools.list_card_products("Visa Gold")
check("одна карта: подсказка открыть её страницу",
      hint_names(r) == ["open_card_product"] and r[actions.HINT_KEY][0]["params"]["slug"] == "visa-gold")
r = tools.list_card_products()
check("список всех карт: кнопок нет", actions.HINT_KEY not in r)

r = tools.search_knowledge("смена ПИН-кода", section="instructions")
check("инструкция по смене PIN: подсказка открыть смену PIN", hint_names(r) == ["open_pin_change"])
r = tools.search_knowledge("овердрафт")
check("другие разделы: подсказки смены PIN нет", "open_pin_change" not in hint_names(r))

FAKE_RATES = {
    "date": "2026-10-16", "note": "тест",
    "cash": [{"currency": "USD", "buy": 87.3, "sell": 87.8}],
    "cashless": [{"currency": "USD", "buy": 87.0, "sell": 87.5}],
    "gold": [],
}
original_rates = eldik_client.get_exchange_rates
eldik_client.get_exchange_rates = lambda: FAKE_RATES
r = tools.get_exchange_rate("usd")
check("курс доллара: подсказка открыть курсы с валютой",
      r[actions.HINT_KEY] == [{"name": "open_exchange_rates", "params": {"currency": "USD"}}])
r = tools.get_exchange_rate()
check("все курсы: подсказка без валюты", hint_names(r) == ["open_exchange_rates"])
actions.take_hints(r)
check("кэш курсов не испорчен подсказкой", actions.HINT_KEY not in FAKE_RATES)
eldik_client.get_exchange_rates = original_rates

# --- цикл агента с заглушкой вместо модели -------------------------------------


class FakeProvider(LLMProvider):
    """Сначала просит указанные инструменты, потом отвечает текстом."""

    def __init__(self, calls):
        self.calls = calls
        self.sent = []
        self.closed = False

    def start_chat(self, history):
        return LLMResponse(text=None, tool_calls=[
            ToolCall(id=f"c{i}", name=name, arguments=args) for i, (name, args) in enumerate(self.calls)
        ])

    def send_tool_results(self, tool_results):
        self.sent.extend(tool_results)
        return LLMResponse(text="Готово.", tool_calls=[])

    def close(self):
        self.closed = True


def run_with(calls, question="Где банкоматы в Оше?"):
    provider = FakeProvider(calls)
    original = agent.create_llm_provider
    agent.create_llm_provider = lambda **kwargs: provider
    try:
        result = agent.run_chat([{"role": "user", "text": question}])
    finally:
        agent.create_llm_provider = original
    return result, provider


result, provider = run_with([("find_locations", {"query": "Ош"})])
check("агент: ответ модели и действие из инструмента",
      result.reply == "Готово." and [a["name"] for a in result.actions] == ["open_locations"])
check("агент: подпись кнопки с городом", result.actions[0]["label"] == "Банкоматы и отделения: Ош")
sent = provider.sent[0]["result"]
check("агент: подсказка не ушла модели", actions.HINT_KEY not in sent)
check("агент: модель знает о кнопке", sent.get("app_buttons") == ["Банкоматы и отделения: Ош"])
check("агент: провайдер закрыт после ответа", provider.closed)

result, _ = run_with([("prepare_transfer", {"phone": "0555 123 456", "amount": 500})],
                     "Переведи 500 сом на 0555 123 456")
check("агент: перевод даёт действие с номером и суммой",
      result.actions == [{"name": "open_transfer_by_phone", "label": "Перевод по номеру телефона",
                          "params": {"currency": "KGS", "phone": "+996555123456", "amount": 500}}])


def bad_hints_tool():
    return {"ok": True, actions.HINT_KEY: [
        {"name": "make_payment", "params": {"amount": 1000000}},
        {"name": "open_card_product", "params": {"slug": "../etc/passwd"}},
        "не словарь",
        {"name": "open_pin_change", "params": {}},
    ]}


def many_hints_tool():
    return {actions.HINT_KEY: [{"name": "open_locations", "params": {"city": c}}
                               for c in ("Ош", "Нарын", "Талас", "Каракол", "Баткен")]}


tools.TOOL_FUNCTIONS["bad_hints_tool"] = bad_hints_tool
tools.TOOL_FUNCTIONS["many_hints_tool"] = many_hints_tool
result, provider = run_with([("bad_hints_tool", {})])
check("агент: неизвестные и неверные действия отброшены, верное осталось",
      [a["name"] for a in result.actions] == ["open_pin_change"])
result, _ = run_with([("many_hints_tool", {})])
check("агент: не больше трёх кнопок под ответом", len(result.actions) == actions.MAX_ACTIONS)
del tools.TOOL_FUNCTIONS["bad_hints_tool"], tools.TOOL_FUNCTIONS["many_hints_tool"]

result, provider = run_with([("find_locations", {"query": "Ош"})], "Какая погода в Бишкеке?")
check("агент: отказ фильтра тем без действий и без вызова модели",
      result.actions == [] and provider.sent == [] and not provider.closed)

print("\nИТОГ:", "ВСЕ ТЕСТЫ ПРОШЛИ" if ok else "ЕСТЬ ПАДЕНИЯ")
sys.exit(0 if ok else 1)
