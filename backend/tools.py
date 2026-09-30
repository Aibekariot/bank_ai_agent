"""
Функции (tools), которые LLM-агент может вызывать.

Правило: всё, что касается реальных цифр банка (ставки, курсы, стоимость
карт) агент обязан получать через эти функции, а не придумывать.
Математику (платежи по кредиту/депозиту) считаем кодом, а не моделью.
"""

import re

import eldik_client

# ---------------------------------------------------------------------------
# Нормализация и поиск
# ---------------------------------------------------------------------------

# На сайте банка встречаются кириллические буквы-двойники внутри латинских
# слов (например "Masterсard" с русской "с"). Приводим оба текста к одному виду.
_HOMOGLYPHS = str.maketrans("аеорсухкмтнв", "aeopcyxkmthb")


def _norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е").translate(_HOMOGLYPHS)


# ВАЖНО: все справочники ниже хранятся УЖЕ в нормализованном виде (через _norm),
# иначе сравнение с нормализованными токенами запроса не сработает.
_STOPWORDS = {_norm(w) for w in [
    "и", "в", "на", "по", "что", "как", "мне", "про", "для", "или", "это", "есть",
    "какой", "какая", "какие", "какое", "сколько", "стоит", "хочу", "расскажи",
    "расскажите", "можно", "банк", "банка", "элдик", "eldik", "у", "вас", "вы",
    "а", "о", "об", "с", "со", "мой", "моя", "нужен", "нужна", "нужно", "подскажите",
    "пожалуйста", "тариф", "условия", "информация", "инфо",
]}

# Общие слова-категории: сами по себе означают "покажи всю категорию".
_GENERIC_STEMS = {_norm(k): v for k, v in {
    "карт": "cards", "card": "cards",
    "кред": "credits", "займ": "credits", "ссуд": "credits",
    "вкла": "deposits", "депо": "deposits", "сбер": "deposits", "накоп": "deposits",
}.items()}

# Слова, которые указывают на категорию, но одновременно являются уточнением
# ("visa" -> искать среди карт именно Visa; "авто" -> среди кредитов именно авто).
_HINT_STEMS = {_norm(k): v for k, v in {
    "visa": "cards", "виза": "cards", "mast": "cards", "маст": "cards",
    "элка": "cards", "elca": "cards", "elka": "cards",
    "ипот": "credits", "авто": "credits", "рассроч": "credits",
}.items()}

# Разные написания одного слова приводим к одному виду.
_SYNONYMS = {_norm(k): _norm(v) for k, v in {
    "элкард": "элкарт", "elcard": "элкарт", "elkart": "элкарт", "эл-карт": "элкарт",
    "мастеркард": "mastercard", "мастер": "mastercard", "виза": "visa",
}.items()}


def _tokens(query: str) -> list[str]:
    raw = re.findall(r"[a-z\u0430-\u044f0-9]+", _norm(query))
    tokens = []
    for tok in raw:
        tok = _SYNONYMS.get(tok, tok)
        if tok in _STOPWORDS or len(tok) < 2:
            continue
        tokens.append(tok)
    return tokens


def _stem(token: str) -> str:
    return token[:4] if len(token) >= 4 else token


def _product_text(product: dict) -> str:
    parts = [product.get("name", ""), product.get("description", "")]
    for key in ("category", "payment_system"):
        parts.append(product.get(key) or "")
    parts.extend(str(v) for v in (product.get("conditions") or {}).values())
    parts.extend(product.get("currencies") or [])
    return _norm(" ".join(parts))


def _category_of(token: str) -> str | None:
    """Категория продуктов, на которую указывает слово (или None)."""
    for stems in (_GENERIC_STEMS, _HINT_STEMS):
        for stem, category in stems.items():
            if token.startswith(stem):
                return category
    return None


def _is_generic(token: str) -> bool:
    """Слово-категория без уточнения ("карта", "кредит", "вклад")."""
    return any(token.startswith(stem) for stem in _GENERIC_STEMS) and not any(
        token.startswith(stem) for stem in _HINT_STEMS
    )


def _compact(product: dict, kind: str) -> dict:
    """Урезанная версия продукта для ответа поиска (экономим токены)."""
    if kind == "cards":
        return {
            "name": product["name"],
            "category": product["category"],
            "payment_system": product["payment_system"],
            "currencies": product["currencies"],
            "issuance_cost": product["issuance_cost"],
            "annual_service_cost": product["annual_service_cost"],
        }
    return {
        "name": product["name"],
        "conditions": product["conditions"],
        "description": product["description"][:200],
    }


def search_bank_products(query: str) -> dict:
    """
    Универсальный поиск по всем продуктам банка (карты, кредиты, депозиты).
    Работает и с расплывчатыми запросами вроде "карта", "вклад", "что-нибудь для пенсионера".

    Args:
        query: запрос пользователя в свободной форме
    """
    catalog = {
        "cards": eldik_client.get_cards(),
        "credits": eldik_client.get_credits(),
        "deposits": eldik_client.get_deposits(),
    }

    tokens = _tokens(query)
    if not tokens:
        # Запрос вообще без содержания - отдаём обзор категорий
        return {
            "query": query,
            "overview": {k: len(v) for k, v in catalog.items()},
            "hint": "Запрос слишком общий. Задай пользователю один уточняющий вопрос: "
            "что его интересует - карты, кредиты или депозиты?",
        }

    generic_tokens = [t for t in tokens if _is_generic(t)]
    specific_tokens = [t for t in tokens if not _is_generic(t)]
    wanted_categories = {c for c in (_category_of(t) for t in tokens) if c}

    # Запрос состоит только из названия категории ("карта", "кредиты") -> обзор категории
    if generic_tokens and not specific_tokens:
        result: dict = {"query": query, "hint": (
            "Запрос общий - дай краткий обзор и задай ОДИН уточняющий вопрос "
            "(тип продукта, валюта, цель)."
        )}
        for category in wanted_categories:
            result[category] = [_compact(p, category) for p in catalog[category]]
        return result

    # Иначе - оценка релевантности по остальным словам
    scored: dict[str, list[tuple[int, dict]]] = {k: [] for k in catalog}
    stems = [_stem(t) for t in specific_tokens]
    for category, products in catalog.items():
        if wanted_categories and category not in wanted_categories:
            continue
        for product in products:
            text = _product_text(product)
            score = sum(1 for s in stems if s in text)
            if score:
                scored[category].append((score, product))

    result = {"query": query}
    total = 0
    for category, items in scored.items():
        items.sort(key=lambda x: -x[0])
        top = [_compact(p, category) for _, p in items[:5]]
        if top:
            result[category] = top
            total += len(top)

    if total == 0:
        result["hint"] = (
            "Ничего не найдено. Не выдумывай продукт. Предложи пользователю уточнить запрос "
            "или обратиться в контакт-центр 9111."
        )
    elif total > 6:
        result["hint"] = "Найдено много вариантов - кратко перечисли и уточни, что интересует."
    return result


# ---------------------------------------------------------------------------
# Каталоги продуктов
# ---------------------------------------------------------------------------

def _filter_by_query(products: list[dict], query: str) -> list[dict]:
    if not query:
        return products
    stems = [_stem(t) for t in _tokens(query)]
    if not stems:
        return products
    return [p for p in products if any(s in _product_text(p) for s in stems)]


def list_card_products(query: str = "") -> list[dict]:
    """
    Список платёжных карт банка (Visa, Mastercard, Элкарт, виртуальные, премиум, бизнес).

    Args:
        query: необязательный фильтр (например "visa", "премиум", "пенсионер", "виртуальная")
    """
    return _filter_by_query(eldik_client.get_cards(), query)


def list_credit_products(query: str = "") -> list[dict]:
    """Список кредитных продуктов банка. query - необязательный фильтр (например "авто")."""
    return _filter_by_query(eldik_client.get_credits(), query)


def list_deposit_products(query: str = "") -> list[dict]:
    """Список депозитных продуктов банка. query - необязательный фильтр."""
    return _filter_by_query(eldik_client.get_deposits(), query)


def get_tariff_documents(query: str = "") -> list[dict]:
    """
    Официальные PDF-документы с тарифами банка (карты, приложение и т.д.).
    Используй, когда стоимость обслуживания/выпуска не указана в карточке продукта.

    Args:
        query: необязательный фильтр по названию документа (например "visa gold", "кредитных карт")
    """
    docs = eldik_client.get_tariff_documents()
    if not query:
        return docs
    stems = [_stem(t) for t in _tokens(query)]
    if not stems:
        return docs
    filtered = [d for d in docs if all(s in _norm(d["title"]) for s in stems)]
    # Если строгий фильтр ничего не дал - ослабляем до "любое слово"
    return filtered or [d for d in docs if any(s in _norm(d["title"]) for s in stems)]


def get_bank_contacts() -> dict:
    """Контакты банка: контакт-центр, телефоны, почта, адрес головного офиса, приложение."""
    return eldik_client.BANK_CONTACTS


# ---------------------------------------------------------------------------
# Курсы валют
# ---------------------------------------------------------------------------

def get_exchange_rate(currency: str = "") -> dict:
    """
    Актуальные курсы валют банка.

    Args:
        currency: код валюты (USD, EUR, RUB, KZT, CNY, TRY, AED, GBP). Пусто = все.
    """
    rates = eldik_client.get_exchange_rates()
    if not currency:
        return rates

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
    }


# ---------------------------------------------------------------------------
# Расчёты (чистая математика)
# ---------------------------------------------------------------------------

def calculate_loan_payment(amount: float, annual_rate_percent: float, term_months: int) -> dict:
    """
    Ежемесячный аннуитетный платёж по кредиту.
    Ставку для конкретного продукта сначала узнай через list_credit_products.

    Args:
        amount: сумма кредита в сомах
        annual_rate_percent: годовая ставка в процентах, например 20
        term_months: срок в месяцах
    """
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
        "note": "Ориентировочный расчёт (аннуитет), реальный график банка может отличаться",
    }


def calculate_deposit_income(amount: float, annual_rate_percent: float, term_months: int) -> dict:
    """
    Доход по депозиту (простые проценты, без капитализации).

    Args:
        amount: сумма вклада
        annual_rate_percent: годовая ставка в процентах
        term_months: срок в месяцах
    """
    if amount <= 0 or term_months <= 0:
        return {"error": "Сумма и срок должны быть положительными числами"}

    total_interest = amount * (annual_rate_percent / 100) * (term_months / 12)
    return {
        "initial_amount": amount,
        "total_interest": round(total_interest, 2),
        "total_payout": round(amount + total_interest, 2),
        "annual_rate_percent": annual_rate_percent,
        "term_months": term_months,
        "note": "Ориентировочный расчёт без капитализации, условия конкретного продукта могут отличаться",
    }


# ---------------------------------------------------------------------------
# Описания функций для Gemini function calling
# ---------------------------------------------------------------------------

_QUERY_PARAM = {"type": "string", "description": "Необязательный текстовый фильтр"}

TOOL_DECLARATIONS = [
    {
        "name": "search_bank_products",
        "description": (
            "Универсальный поиск по ВСЕМ продуктам банка (карты, кредиты, депозиты). "
            "Используй ПЕРВЫМ, когда запрос расплывчатый или непонятно, к какой категории он относится "
            "(например: 'карта', 'вклад', 'что есть для пенсионера', 'visa')."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Запрос пользователя как есть"}},
            "required": ["query"],
        },
    },
    {
        "name": "list_card_products",
        "description": "Список платёжных карт банка: категория, платёжная система, валюты, стоимость выпуска и обслуживания",
        "parameters": {"type": "object", "properties": {"query": _QUERY_PARAM}},
    },
    {
        "name": "list_credit_products",
        "description": "Список кредитных продуктов банка с условиями (ставка, сумма, срок)",
        "parameters": {"type": "object", "properties": {"query": _QUERY_PARAM}},
    },
    {
        "name": "list_deposit_products",
        "description": "Список депозитных продуктов банка с условиями (ставка, минимальная сумма, срок, выплата процентов)",
        "parameters": {"type": "object", "properties": {"query": _QUERY_PARAM}},
    },
    {
        "name": "get_tariff_documents",
        "description": "Ссылки на официальные PDF с тарифами банка. Используй, если стоимость не указана в карточке продукта",
        "parameters": {"type": "object", "properties": {"query": _QUERY_PARAM}},
    },
    {
        "name": "get_bank_contacts",
        "description": "Контакты банка: контакт-центр, телефоны, email, адрес головного офиса, ссылки на мобильное приложение",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_exchange_rate",
        "description": "Актуальный курс валют банка (наличный и безналичный)",
        "parameters": {
            "type": "object",
            "properties": {
                "currency": {
                    "type": "string",
                    "description": "Код валюты: USD, EUR, RUB, KZT, CNY, TRY, AED, GBP. Пусто = все валюты",
                }
            },
        },
    },
    {
        "name": "calculate_loan_payment",
        "description": "Рассчитать ежемесячный платёж по кредиту (аннуитет)",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Сумма кредита в сомах"},
                "annual_rate_percent": {"type": "number", "description": "Годовая ставка в процентах, например 20"},
                "term_months": {"type": "integer", "description": "Срок кредита в месяцах"},
            },
            "required": ["amount", "annual_rate_percent", "term_months"],
        },
    },
    {
        "name": "calculate_deposit_income",
        "description": "Рассчитать доход по депозиту",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Сумма вклада в сомах"},
                "annual_rate_percent": {"type": "number", "description": "Годовая ставка в процентах, например 12"},
                "term_months": {"type": "integer", "description": "Срок вклада в месяцах"},
            },
            "required": ["amount", "annual_rate_percent", "term_months"],
        },
    },
]

TOOL_FUNCTIONS = {
    "search_bank_products": search_bank_products,
    "list_card_products": list_card_products,
    "list_credit_products": list_credit_products,
    "list_deposit_products": list_deposit_products,
    "get_tariff_documents": get_tariff_documents,
    "get_bank_contacts": get_bank_contacts,
    "get_exchange_rate": get_exchange_rate,
    "calculate_loan_payment": calculate_loan_payment,
    "calculate_deposit_income": calculate_deposit_income,
}
