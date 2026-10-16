"""
Функции (tools), которые LLM-агент может вызывать.

Правило: всё, что касается реальных цифр банка (ставки, курсы, стоимость
карт), агент обязан получать через эти функции, а не придумывать.

Откуда берутся данные:
  * продукты и услуги (карты, кредиты, депозиты, переводы, мобильный
    банкинг и т.д.) - из локальной базы знаний через модуль knowledge.py;
    во время ответа клиенту обращений к сайту банка и к PostgreSQL нет;
  * курсы валют - живой запрос к сайту (они меняются каждый день);
  * контакты банка - словарь в eldik_client.py;
  * расчёты (платёж по кредиту, доход по депозиту) - обычный Python-код;
  * кнопки в приложении - подсказки под ключом actions.HINT_KEY; агент
    проверяет их по contract/actions.json и убирает из ответа модели.

Названия инструментов и их основные поля сохранены, поэтому системный
промпт в agent.py продолжает работать.
"""

from datetime import date

import actions
import knowledge
import eldik_client


# ---------------------------------------------------------------------------
# Вспомогательные функции форматирования данных для модели
# ---------------------------------------------------------------------------

MAX_TEXT_CHARS = 3000  # длинные тексты обрезаем, чтобы не тратить токены


def _clip(text: str, limit: int = MAX_TEXT_CHARS) -> tuple[str, bool]:
    text = text or ""
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + "…", True


def _conditions_dict(conditions: list[dict]) -> dict:
    """[{key, value}, ...] -> {key: value}. Повторяющиеся ключи склеиваем."""
    result: dict[str, str] = {}
    for item in conditions or []:
        key = (item.get("key") or "").strip()
        value = (item.get("value") or "").strip()
        if not key and not value:
            continue
        if key in result:
            result[key] = f"{result[key]}; {value}"
        else:
            result[key] = value
    return result


def _documents(docs: list[dict], limit: int = 6) -> list[dict]:
    return [
        {"title": d.get("title"), "url": d.get("url")}
        for d in (docs or [])[:limit]
        if d.get("url")
    ]


def _meta(doc: dict) -> dict:
    return {
        "official_page": doc.get("source_url"),
        "data_date": doc.get("data_date"),
    }


def _data_level(doc: dict) -> dict:
    """Честно сообщаем модели, если по продукту есть только краткие данные."""
    if doc.get("detail_level") == "list":
        return {
            "data_level": (
                "краткие данные: детальная страница продукта в базе отсутствует; "
                "если нужной подробности нет, скажи, что она не указана"
            )
        }
    return {}


COMPACT_AFTER = 3        # если продуктов больше, отдаём краткий вид
COMPACT_TEXT_CHARS = 400  # размер описания в кратком виде

_FEE_WORDS = ("обслуж", "открытие", "остаток", "перевыпуск", "выпуск", "стоимост")


def _compact_text(text: str, limit: int = COMPACT_TEXT_CHARS) -> str:
    """Для списков: оставляем строки про стоимость, остальное отбрасываем."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    fee = [l for l in lines if any(w in l.lower() for w in _FEE_WORDS)]
    picked = "\n".join(fee) if fee else (lines[0] if lines else "")
    return _clip(picked, limit)[0]


def _card_view(doc: dict, compact: bool = False) -> dict:
    a = doc.get("attributes", {})
    if compact:
        text, truncated = _compact_text(doc.get("text", "")), False
    else:
        text, truncated = _clip(doc.get("text", ""))
    view = {
        "name": doc.get("title"),
        "category": a.get("category"),
        "payment_system": a.get("payment_system"),
        "audience": a.get("audience"),
        "currencies": a.get("currencies") or [],
        "issuance_cost": a.get("issuance"),
        "annual_service_cost": a.get("annual_service"),
        "account_opening": a.get("account_opening"),
        "card_expiration_date": a.get("card_expiration_date"),
        # В details лежат условия с детальной страницы карты (обслуживание,
        # остаток, перевыпуск, преимущества). Если issuance_cost или
        # annual_service_cost равны null, проверь details.
        "details": text,
    }
    if compact:
        # В списке без документов и длинных текстов: так ответ приходит
        # быстрее. Подробности - отдельным запросом по названию карты.
        view["more"] = "Подробности и документы: запроси эту карту по названию"
    else:
        view["documents"] = _documents(doc.get("documents"))
    if truncated:
        view["details_truncated"] = True
    view.update(_data_level(doc))
    view.update(_meta(doc))
    return view


def _product_view(doc: dict, compact: bool = False) -> dict:
    """Кредиты, депозиты, исламские продукты, переводы."""
    text, truncated = _clip(doc.get("text", ""), COMPACT_TEXT_CHARS if compact else MAX_TEXT_CHARS)
    view = {
        "name": doc.get("title"),
        "conditions": _conditions_dict(doc.get("conditions")),
        "description": text,
    }
    attrs = doc.get("attributes", {})
    if attrs.get("is_available") is False:
        view["is_available"] = False
    if doc.get("documents") and not compact:
        view["documents"] = _documents(doc["documents"])
    if truncated:
        view["description_truncated"] = True
    view.update(_data_level(doc))
    view.update(_meta(doc))
    return view


def _today() -> date:
    """Сегодняшняя дата; вынесена в функцию, чтобы тесты могли её подменить."""
    return date.today()


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _validity(doc: dict) -> dict:
    """
    Сроки программ партнёров. Сравниваются с сегодняшней датой при каждом
    ответе: данные собраны раньше, и срок мог истечь уже после сборки.
    """
    attrs = doc.get("attributes") or {}
    today = _today()
    out: dict = {}

    until = _parse_date(attrs.get("valid_until"))
    if until:
        if until < today:
            out["validity_warning"] = (
                f"Срок программы, указанный на странице банка, истёк {_fmt_date(until)}. "
                "Не говори, что услуга действует сейчас: назови заявленную дату "
                "и посоветуй уточнить актуальность в банке (9111)."
            )
        else:
            out["valid_until"] = _fmt_date(until)

    offers = attrs.get("offers")
    if offers:
        active, expired = [], []
        for o in offers:
            d = _parse_date(o.get("valid_until"))
            item = {"partner": o.get("partner"), "benefit": o.get("benefit"),
                    "valid_until": _fmt_date(d) if d else None}
            (expired if d and d < today else active).append(item)
        out["offers_active"] = active
        if expired:
            out["offers_expired"] = [f"{e['partner']} (до {e['valid_until']})" for e in expired]
            out["offers_note"] = (
                "Предложения из offers_expired по данным страницы закончились. "
                "Не предлагай их как действующие; можно упомянуть, что срок прошёл."
            )
    if out:
        out["today"] = today.isoformat()
    return out


def _generic_view(doc: dict, text_limit: int = MAX_TEXT_CHARS) -> dict:
    text, truncated = _clip(doc.get("text", ""), text_limit)
    view = {
        "title": doc.get("title"),
        "section": doc.get("section"),
        "text": text,
    }
    conditions = _conditions_dict(doc.get("conditions"))
    if conditions:
        view["conditions"] = conditions
    if doc.get("documents"):
        view["documents"] = _documents(doc["documents"])
    if truncated:
        view["text_truncated"] = True
    view.update(_validity(doc))
    view.update(_data_level(doc))
    view.update(_meta(doc))
    return view


def _view_for(doc: dict, text_limit: int = MAX_TEXT_CHARS) -> dict:
    if doc["section"] == "cards":
        return _card_view(doc)
    if doc["section"] in ("credits", "deposits", "islamic", "transfers"):
        view = _product_view(doc)
        view["section"] = doc["section"]
        return view
    return _generic_view(doc, text_limit)


NOT_FOUND_HINT = (
    "Ничего не найдено. Не выдумывай продукт или условия. "
    "Предложи уточнить запрос или обратиться в контакт-центр 9111."
)


def _safe(func):
    """Если база знаний не найдена, агент получает понятную ошибку, а не падение."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except knowledge.KnowledgeError as exc:
            print(f"[KNOWLEDGE ERROR] {exc}")
            return {
                "error": (
                    "База знаний временно недоступна. Не отвечай по памяти. "
                    "Предложи обратиться в контакт-центр 9111."
                )
            }

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def _listing(section: str, query: str, view) -> dict:
    docs, _filtered = knowledge.filter_section(section, query)
    if not docs:
        return {"count": 0, "items": [], "hint": NOT_FOUND_HINT}
    compact = len(docs) > COMPACT_AFTER
    result = {"count": len(docs), "items": [view(d, compact=compact) for d in docs]}
    if compact:
        result["note"] = (
            "Краткий список: основные ставки и условия. Подробности по "
            "конкретному продукту запроси по его названию."
        )
    return result


# ---------------------------------------------------------------------------
# Карты
# ---------------------------------------------------------------------------

_BUSINESS_WORDS = ("бизнес", "ип ", "юридичес", "предпринимател", "business")


@_safe
def list_card_products(query: str = "") -> dict:
    """
    Основной инструмент для любых вопросов о банковских картах.

    Пустой query возвращает карты для физических лиц. Бизнес-карты
    показываются только если пользователь явно спрашивает о них.
    """
    q = (query or "").lower() + " "
    wants_business = any(w in q for w in _BUSINESS_WORDS)

    docs, _filtered = knowledge.filter_section("cards", query)
    if not wants_business:
        docs = [d for d in docs if d["attributes"].get("audience") != "business"]

    if not docs:
        return {"count": 0, "items": [], "hint": NOT_FOUND_HINT}

    compact = len(docs) > COMPACT_AFTER
    result = {"count": len(docs), "items": [_card_view(d, compact=compact) for d in docs]}
    if not compact:
        # Подсказка приложению: кнопка "открыть карту" (модели не показывается).
        result[actions.HINT_KEY] = [
            {"name": "open_card_product", "params": {"slug": d.get("slug"), "title": d.get("title")}}
            for d in docs
        ]
    return result


# ---------------------------------------------------------------------------
# Кредиты и депозиты
# ---------------------------------------------------------------------------

@_safe
def list_credit_products(query: str = "") -> dict:
    """Кредитные продукты банка (краткие условия и, где есть, детали)."""
    return _listing("credits", query, _product_view)


@_safe
def list_deposit_products(query: str = "") -> dict:
    """Депозитные продукты банка."""
    return _listing("deposits", query, _product_view)


# ---------------------------------------------------------------------------
# Банкоматы, отделения, кассы
# ---------------------------------------------------------------------------

_KIND_RU = {
    "atm": "Банкомат",
    "branch": "Филиал / отделение",
    "savings_cash": "Сберегательная касса",
    "mobile_cash": "Выездная касса",
    "other": "Точка обслуживания",
}


def _location_view(item: dict) -> dict:
    view = {
        "type": _KIND_RU.get(item.get("kind"), "Точка обслуживания"),
        "name": item.get("name"),
        "address": item.get("address"),
        "city": item.get("city"),
        "region": item.get("region"),
        "phones": item.get("phones") or [],
    }
    if item.get("lat") is not None and item.get("lng") is not None:
        # Ссылку на карту строит код, а не модель.
        view["map_link"] = f"https://www.google.com/maps?q={item['lat']},{item['lng']}"
    return view


@_safe
def find_locations(query: str = "", kind: str = "") -> dict:
    """Банкоматы, филиалы и кассы банка: поиск по городу, области или улице."""
    result = knowledge.find_locations(query, kind, limit=8)
    out = {
        "total": result["total"],
        "shown": len(result["items"]),
        "items": [_location_view(i) for i in result["items"]],
        "coverage": result["coverage"],
        "data_date": result["data_date"],
        "note": (
            "Режим работы и текущий статус в данных не указаны: не называй "
            "время работы, не говори что точка открыта или закрыта, предложи "
            "уточнить в контакт-центре 9111. coverage - сколько таких точек "
            "в каждом регионе: если нужного города там нет, скажи что у тебя "
            "нет данных по этому городу."
        ),
    }
    if result["total"] == 0:
        out["hint"] = (
            "Ничего не найдено по этому запросу. Не выдумывай адреса. "
            "Назови регионы из coverage или предложи позвонить в 9111."
        )
    else:
        params = {"city": query.strip()} if (query or "").strip() else {}
        if kind:
            params["kind"] = kind
        out[actions.HINT_KEY] = [{"name": "open_locations", "params": params}]
    return out


# ---------------------------------------------------------------------------
# Тарифы
# ---------------------------------------------------------------------------

@_safe
def get_tariff_documents(query: str = "") -> dict:
    """
    Официальные документы с тарифами банка (названия и ссылки на PDF).

    Текст самих PDF в базе знаний пока не хранится, поэтому цифры из этих
    документов агент назвать не может: он даёт название и ссылку.
    """
    docs, _filtered = knowledge.filter_section("tariffs", query)
    if not docs:
        return {"count": 0, "items": [], "hint": NOT_FOUND_HINT}

    items = []
    for doc in docs:
        for d in doc.get("documents", []):
            items.append({"title": d.get("title"), "url": d.get("url")})

    return {
        "count": len(items),
        "items": items,
        "note": (
            "Это только список документов. Цифры внутри документов тебе "
            "недоступны: не называй суммы, дай название документа. "
            "Список может быть неполным."
        ),
        "data_date": docs[0].get("data_date"),
    }


# ---------------------------------------------------------------------------
# Поиск по остальным разделам
# ---------------------------------------------------------------------------

# Инструкция по смене PIN: если она найдена, приложение покажет кнопку смены PIN.
PIN_CHANGE_DOC_ID = "instructions/change-pin-code"

SEARCHABLE_SECTIONS = [
    "cards",
    "credits",
    "deposits",
    "overdraft",
    "transfers",
    "accounts",
    "islamic",
    "salary_project",
    "mobile_banking",
    "instructions",
    "card_privileges",
    "tariffs",
]


@_safe
def search_knowledge(query: str, section: str = "") -> dict:
    """
    Поиск по базе знаний банка: овердрафт, переводы, открытие счёта,
    исламское финансирование, зарплатный проект, мобильный банкинг.
    """
    sections = [section] if section in SEARCHABLE_SECTIONS else None
    docs = knowledge.search(query, sections=sections, limit=4)

    if not docs:
        return {"count": 0, "items": [], "hint": NOT_FOUND_HINT}

    result = {"count": len(docs), "items": [_view_for(d) for d in docs]}
    if any(d["id"] == PIN_CHANGE_DOC_ID for d in docs):
        result[actions.HINT_KEY] = [{"name": "open_pin_change", "params": {}}]
    return result


@_safe
def search_bank_products(query: str) -> dict:
    """
    Универсальный поиск по всем разделам, когда категорию определить нельзя.
    Возвращает краткие результаты.
    """
    if not knowledge.query_stems(query):
        status = knowledge.status()
        return {
            "query": query,
            "overview": {
                k: v for k, v in status["sections"].items()
                if k in SEARCHABLE_SECTIONS
            },
            "hint": "Запрос слишком общий. Уточни, что именно интересует.",
        }

    docs = knowledge.search(query, limit=6)
    if not docs:
        return {"query": query, "count": 0, "items": [], "hint": NOT_FOUND_HINT}

    result = {
        "query": query,
        "count": len(docs),
        "items": [_view_for(d, text_limit=400) for d in docs],
    }
    if len(docs) >= 6:
        result["hint"] = (
            "Найдено много вариантов. Кратко перечисли их и уточни, "
            "что именно интересует пользователя."
        )
    return result


# ---------------------------------------------------------------------------
# Контакты
# ---------------------------------------------------------------------------

def get_bank_contacts() -> dict:
    """Контакты банка."""
    return eldik_client.BANK_CONTACTS


# ---------------------------------------------------------------------------
# Курсы валют (живые данные, меняются каждый день)
# ---------------------------------------------------------------------------

def get_exchange_rate(currency: str = "") -> dict:
    """
    Актуальные курсы валют банка.

    Пустой currency возвращает все валюты.
    """
    rates = eldik_client.get_exchange_rates()

    if not currency:
        # Копия: rates лежит в кэше клиента, его нельзя менять.
        result = dict(rates)
        result[actions.HINT_KEY] = [{"name": "open_exchange_rates", "params": {}}]
        return result

    currency = currency.upper()
    cash = next((r for r in rates["cash"] if r["currency"] == currency), None)
    cashless = next((r for r in rates["cashless"] if r["currency"] == currency), None)

    if not cash and not cashless:
        return {"error": f"Валюта {currency} не найдена в списке банка"}

    return {
        "date": rates["date"],
        "currency": currency,
        "cash": cash,
        "cashless": cashless,
        "note": rates["note"],
        actions.HINT_KEY: [{"name": "open_exchange_rates", "params": {"currency": currency}}],
    }


# ---------------------------------------------------------------------------
# Черновик перевода по номеру телефона
# ---------------------------------------------------------------------------

TRANSFER_CURRENCIES = ("KGS",)  # как в contract/actions.json


def _parse_amount(amount) -> float | None:
    """Сумма из аргумента модели: число или строка вида "1 500,50"."""
    if amount is None or isinstance(amount, bool):
        return None
    if isinstance(amount, (int, float)):
        return float(amount)
    try:
        return float(str(amount).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def prepare_transfer(phone: str = "", amount=None, currency: str = "KGS") -> dict:
    """
    Черновик перевода по номеру телефона для приложения.

    Перевод НЕ проводится: приложение откроет форму с этими данными,
    клиент проверит их и подтвердит перевод сам.
    """
    currency = (currency or "KGS").strip().upper()
    if currency in ("СОМ", "СОМОВ", "SOM", "KGZ"):
        currency = "KGS"
    if currency not in TRANSFER_CURRENCIES:
        return {
            "status": "unsupported_currency",
            "hint": (
                "Подготовить можно только перевод в сомах (KGS). Перевод не подготовлен: "
                "скажи это клиенту и не называй других условий."
            ),
        }

    params: dict = {"currency": "KGS"}
    result: dict = {"status": "draft_ready", "currency": "KGS"}
    missing = []

    if (phone or "").strip():
        normalized = actions.normalize_kg_phone(phone)
        if normalized is None:
            return {
                "status": "need_phone",
                "hint": (
                    "Номер не распознан, перевод не подготовлен. Попроси номер мобильного "
                    "телефона получателя, например 0555 123 456."
                ),
            }
        params["phone"] = result["phone"] = normalized
    else:
        missing.append("Номер получателя не указан: клиент введёт его в форме.")

    if amount is not None:
        value = _parse_amount(amount)
        if value is None or value < 1:
            return {
                "status": "need_amount",
                "hint": "Сумма не распознана, перевод не подготовлен. Попроси сумму в сомах.",
            }
        value = int(value) if value.is_integer() else round(value, 2)
        params["amount"] = result["amount"] = value
    else:
        missing.append("Сумма не указана: клиент введёт её в форме.")

    result["note"] = " ".join([
        "Перевод НЕ выполнен. В приложении откроется форма перевода с этими данными.",
        "Скажи клиенту коротко: форма готова, нужно проверить данные и подтвердить",
        "перевод в приложении. Никогда не пиши, что деньги отправлены.",
        *missing,
    ])
    result[actions.HINT_KEY] = [{"name": "open_transfer_by_phone", "params": params}]
    return result


# ---------------------------------------------------------------------------
# Расчёт кредита
# ---------------------------------------------------------------------------

def calculate_loan_payment(
    amount: float,
    annual_rate_percent: float,
    term_months: int
) -> dict:
    """Ежемесячный аннуитетный платёж."""

    if amount <= 0 or term_months <= 0:
        return {"error": "Сумма и срок должны быть положительными числами"}

    monthly_rate = annual_rate_percent / 100 / 12

    if monthly_rate == 0:
        monthly_payment = amount / term_months
    else:
        factor = (1 + monthly_rate) ** term_months
        monthly_payment = amount * monthly_rate * factor / (factor - 1)

    total_payment = monthly_payment * term_months

    return {
        "monthly_payment": round(monthly_payment, 2),
        "total_payment": round(total_payment, 2),
        "overpayment": round(total_payment - amount, 2),
        "amount": amount,
        "annual_rate_percent": annual_rate_percent,
        "term_months": term_months,
        "note": (
            "Ориентировочный расчёт (аннуитет), "
            "реальный график банка может отличаться"
        ),
    }


# ---------------------------------------------------------------------------
# Расчёт депозита
# ---------------------------------------------------------------------------

def calculate_deposit_income(
    amount: float,
    annual_rate_percent: float,
    term_months: int
) -> dict:
    """Доход по депозиту без капитализации."""

    if amount <= 0 or term_months <= 0:
        return {"error": "Сумма и срок должны быть положительными числами"}

    total_interest = amount * (annual_rate_percent / 100) * (term_months / 12)

    return {
        "initial_amount": amount,
        "total_interest": round(total_interest, 2),
        "total_payout": round(amount + total_interest, 2),
        "annual_rate_percent": annual_rate_percent,
        "term_months": term_months,
        "note": (
            "Ориентировочный расчёт без капитализации, "
            "условия конкретного продукта могут отличаться"
        ),
    }


# ---------------------------------------------------------------------------
# Описания функций для LLM
# ---------------------------------------------------------------------------

_QUERY_PARAM = {
    "type": "string",
    "description": "Необязательный текстовый фильтр",
}


TOOL_DECLARATIONS = [
    {
        "name": "search_bank_products",
        "description": (
            "Универсальный поиск по банковским продуктам и услугам. "
            "Используй, если невозможно определить категорию."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Запрос пользователя как есть",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_knowledge",
        "description": (
            "Поиск по базе знаний банка для вопросов НЕ про карты, кредиты "
            "и депозиты: овердрафт, денежные переводы (SWIFT, Western Union, "
            "MoneyGram и др.), открытие банковского счёта, исламское "
            "финансирование (мурабаха), зарплатный проект, мобильный банкинг "
            "и как его подключить. Возвращает текст раздела, условия, "
            "документы и дату данных."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "О чём спрашивает пользователь, ключевые слова",
                },
                "section": {
                    "type": "string",
                    "description": "Необязательно: раздел, чтобы сузить поиск",
                    "enum": SEARCHABLE_SECTIONS,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_card_products",
        "description": (
            "ОСНОВНОЙ инструмент для любых вопросов "
            "о банковских картах. Используй для запросов: "
            "какие карты есть, стоимость карты, выпуск, "
            "обслуживание, Visa, Mastercard, Элкарт, "
            "виртуальные, дебетовые, премиальные, пенсионные "
            "и другие карты. Пустой query возвращает карты "
            "для физических лиц."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": _QUERY_PARAM},
        },
    },
    {
        "name": "list_credit_products",
        "description": (
            "Основной инструмент для вопросов о кредитах. "
            "Возвращает доступные условия продуктов."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": _QUERY_PARAM},
        },
    },
    {
        "name": "list_deposit_products",
        "description": (
            "Основной инструмент для вопросов о депозитах "
            "и вкладах. Возвращает доступные условия продуктов."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": _QUERY_PARAM},
        },
    },
    {
        "name": "get_tariff_documents",
        "description": (
            "Официальные документы с тарифами банка (названия и ссылки). "
            "Используй, если стоимость выпуска или обслуживания "
            "не указана в данных продукта."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": _QUERY_PARAM},
        },
    },
    {
        "name": "find_locations",
        "description": (
            "Банкоматы, филиалы (отделения) и кассы банка с адресами и "
            "телефонами. Используй на вопросы 'где банкомат', 'где отделение', "
            "'адрес филиала в Оше'. Режим работы в данных отсутствует."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Город, область, улица или название. Пусто = все точки.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["atm", "branch", "savings_cash", "mobile_cash"],
                    "description": (
                        "atm = банкомат, branch = филиал/отделение, "
                        "savings_cash = сберегательная касса, "
                        "mobile_cash = выездная касса. Пусто = любой тип."
                    ),
                },
            },
        },
    },
    {
        "name": "get_bank_contacts",
        "description": (
            "Контакты банка. Используй только если пользователь "
            "прямо спрашивает номер телефона, адрес, WhatsApp, "
            "email или как связаться с банком."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_exchange_rate",
        "description": "Актуальный курс валют банка (наличный и безналичный).",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "description": (
                        "Код валюты: USD, EUR, RUB, KZT, "
                        "CNY, TRY, AED, GBP. Пусто = все валюты."
                    ),
                },
            },
        },
    },
    {
        "name": "prepare_transfer",
        "description": (
            "Подготовить в приложении форму перевода по номеру телефона, когда клиент "
            "САМ просит перевести деньги (например: «переведи 500 сом на 0555 123 456»). "
            "Перевод не проводится: клиент проверит данные и подтвердит его в приложении. "
            "Не используй для вопросов об условиях, комиссиях и способах переводов "
            "(для них search_knowledge)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Номер получателя из сообщения клиента, как написан. Пусто, если не указан.",
                },
                "amount": {
                    "type": "number",
                    "description": "Сумма из сообщения клиента. Не указывай, если клиент её не назвал.",
                },
                "currency": {
                    "type": "string",
                    "description": "Валюта суммы: KGS (сом), USD и т.д. По умолчанию KGS.",
                },
            },
        },
    },
    {
        "name": "calculate_loan_payment",
        "description": "Рассчитать ежемесячный платёж по кредиту (аннуитет).",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Сумма кредита в сомах",
                },
                "annual_rate_percent": {
                    "type": "number",
                    "description": "Годовая ставка в процентах",
                },
                "term_months": {
                    "type": "integer",
                    "description": "Срок кредита в месяцах",
                },
            },
            "required": ["amount", "annual_rate_percent", "term_months"],
        },
    },
    {
        "name": "calculate_deposit_income",
        "description": "Рассчитать доход по депозиту.",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Сумма вклада в сомах",
                },
                "annual_rate_percent": {
                    "type": "number",
                    "description": "Годовая ставка в процентах",
                },
                "term_months": {
                    "type": "integer",
                    "description": "Срок вклада в месяцах",
                },
            },
            "required": ["amount", "annual_rate_percent", "term_months"],
        },
    },
]


# ---------------------------------------------------------------------------
# Реестр функций
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "search_bank_products": search_bank_products,
    "search_knowledge": search_knowledge,
    "list_card_products": list_card_products,
    "list_credit_products": list_credit_products,
    "list_deposit_products": list_deposit_products,
    "get_tariff_documents": get_tariff_documents,
    "find_locations": find_locations,
    "get_bank_contacts": get_bank_contacts,
    "get_exchange_rate": get_exchange_rate,
    "prepare_transfer": prepare_transfer,
    "calculate_loan_payment": calculate_loan_payment,
    "calculate_deposit_income": calculate_deposit_income,
}
