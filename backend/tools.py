"""
Функции (tools), которые LLM-агент может вызывать.

Правило: всё, что касается реальных цифр банка
(ставки, курсы, стоимость карт) агент обязан получать
через эти функции, а не придумывать.

Математику (платежи по кредиту/депозиту)
считаем кодом, а не моделью.
"""

import re

from database import get_connection
import eldik_client


# ---------------------------------------------------------------------------
# Нормализация и поиск
# ---------------------------------------------------------------------------

# На сайте банка встречаются кириллические буквы-двойники
# внутри латинских слов.
_HOMOGLYPHS = str.maketrans(
    "аеорсухкмтнв",
    "aeopcyxkmthb"
)


def _norm(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("ё", "е")
        .translate(_HOMOGLYPHS)
    )


_STOPWORDS = {
    _norm(w)
    for w in [
        "и",
        "в",
        "на",
        "по",
        "что",
        "как",
        "мне",
        "про",
        "для",
        "или",
        "это",
        "есть",
        "какой",
        "какая",
        "какие",
        "какое",
        "сколько",
        "стоит",
        "хочу",
        "расскажи",
        "расскажите",
        "можно",
        "банк",
        "банка",
        "элдик",
        "eldik",
        "у",
        "вас",
        "вы",
        "а",
        "о",
        "об",
        "с",
        "со",
        "мой",
        "моя",
        "нужен",
        "нужна",
        "нужно",
        "подскажите",
        "пожалуйста",
        "тариф",
        "условия",
        "информация",
        "инфо",
    ]
}


# Общие слова-категории.
_GENERIC_STEMS = {
    _norm(k): v
    for k, v in {
        "карт": "cards",
        "card": "cards",

        "кред": "credits",
        "займ": "credits",
        "ссуд": "credits",

        "вкла": "deposits",
        "депо": "deposits",
        "сбер": "deposits",
        "накоп": "deposits",
    }.items()
}


# Слова, которые указывают на категорию,
# но одновременно являются уточнением.
_HINT_STEMS = {
    _norm(k): v
    for k, v in {
        "visa": "cards",
        "виза": "cards",

        "mast": "cards",
        "маст": "cards",

        "элка": "cards",
        "elca": "cards",
        "elka": "cards",

        "ипот": "credits",
        "авто": "credits",
        "рассроч": "credits",
    }.items()
}


_SYNONYMS = {
    _norm(k): _norm(v)
    for k, v in {
        "элкард": "элкарт",
        "elcard": "элкарт",
        "elkart": "элкарт",
        "эл-карт": "элкарт",

        "мастеркард": "mastercard",
        "мастер": "mastercard",

        "виза": "visa",
    }.items()
}


def _tokens(query: str) -> list[str]:

    raw = re.findall(
        r"[a-z\u0430-\u044f0-9]+",
        _norm(query)
    )

    tokens = []

    for tok in raw:

        tok = _SYNONYMS.get(
            tok,
            tok
        )

        if tok in _STOPWORDS:
            continue

        if len(tok) < 2:
            continue

        tokens.append(tok)

    return tokens


def _stem(token: str) -> str:

    if len(token) >= 4:
        return token[:4]

    return token


def _product_text(product: dict) -> str:
    """
    Формирует поисковый текст из данных банковского продукта.
    Поддерживает структуру данных из PostgreSQL.
    """

    category = product.get("category") or {}
    payment_system = product.get("payment_system") or {}

    currencies = product.get("currencies") or []

    currency_text = " ".join(
        str(currency.get("code", ""))
        for currency in currencies
        if isinstance(currency, dict)
    )

    parts = [
        product.get("name"),
        category.get("name"),
        payment_system.get("name"),
        currency_text,
        product.get("issuance"),
        product.get("annual_service"),
        product.get("account_opening"),
        product.get("short_desc"),
    ]

    return " ".join(
        str(part)
        for part in parts
        if part
    )


def _category_of(token: str) -> str | None:
    """
    Категория продукта,
    на которую указывает слово.
    """

    for stems in (
        _GENERIC_STEMS,
        _HINT_STEMS,
    ):

        for stem, category in stems.items():

            if token.startswith(stem):
                return category

    return None


def _is_generic(token: str) -> bool:
    """
    Слово-категория без уточнения:
    "карта", "кредит", "вклад".
    """

    return (
        any(
            token.startswith(stem)
            for stem in _GENERIC_STEMS
        )
        and not any(
            token.startswith(stem)
            for stem in _HINT_STEMS
        )
    )


def _compact(product: dict, kind: str) -> dict:
    """
    Формирует минимальный набор данных для LLM.
    Внутренняя структура PostgreSQL не передаётся модели.
    """

    if kind == "cards":

        category = product.get("category") or {}
        payment_system = product.get("payment_system") or {}
        currencies = product.get("currencies") or []

        return {
            "name": product.get("name"),
            "category": category.get("name"),
            "payment_system": payment_system.get("name"),
            "currencies": [
                currency.get("code")
                for currency in currencies
                if isinstance(currency, dict)
                and currency.get("code")
            ],
            "issuance_cost": product.get("issuance"),
            "annual_service_cost": product.get("annual_service"),
        }

    return {
        "name": product.get("name"),
        "conditions": product.get("conditions") or {},
        "description": (
            product.get("description") or ""
        )[:200],
    }


# ---------------------------------------------------------------------------
# Универсальный поиск
# ---------------------------------------------------------------------------

def search_bank_products(query: str) -> dict:
    """
    Универсальный поиск по всем продуктам банка.

    Используется только тогда, когда невозможно определить
    конкретную категорию продукта.

    Для конкретных запросов о картах, кредитах или депозитах
    лучше использовать специализированные функции.
    """

    catalog = {
        "cards": eldik_client.get_cards(),
        "credits": eldik_client.get_credits(),
        "deposits": eldik_client.get_deposits(),
    }

    tokens = _tokens(query)

    if not tokens:

        return {
            "query": query,

            "overview": {
                k: len(v)
                for k, v in catalog.items()
            },

            "hint": (
                "Запрос слишком общий. "
                "Уточни: карты, кредиты или депозиты."
            ),
        }

    generic_tokens = [
        t
        for t in tokens
        if _is_generic(t)
    ]

    specific_tokens = [
        t
        for t in tokens
        if not _is_generic(t)
    ]

    wanted_categories = {
        c
        for c in (
            _category_of(t)
            for t in tokens
        )
        if c
    }

    # Если запрос состоит только
    # из названия категории.
    if generic_tokens and not specific_tokens:

        result = {
            "query": query,

            "hint": (
                "Запрос общий. "
                "Дай краткий обзор и задай "
                "один уточняющий вопрос."
            ),
        }

        for category in wanted_categories:

            result[category] = [
                _compact(
                    p,
                    category
                )
                for p in catalog[category]
            ]

        return result

    # Оценка релевантности.
    scored = {
        k: []
        for k in catalog
    }

    stems = [
        _stem(t)
        for t in specific_tokens
    ]

    for category, products in catalog.items():

        if (
            wanted_categories
            and category not in wanted_categories
        ):
            continue

        for product in products:

            text = _product_text(product)

            score = sum(
                1
                for s in stems
                if s in text
            )

            if score:
                scored[category].append(
                    (
                        score,
                        product
                    )
                )

    result = {
        "query": query
    }

    total = 0

    for category, items in scored.items():

        items.sort(
            key=lambda x: -x[0]
        )

        top = [
            _compact(
                p,
                category
            )
            for _, p in items[:5]
        ]

        if top:

            result[category] = top
            total += len(top)

    if total == 0:

        result["hint"] = (
            "Ничего не найдено. "
            "Не выдумывай продукт. "
            "Предложи пользователю уточнить запрос "
            "или обратиться в контакт-центр 9111."
        )

    elif total > 6:

        result["hint"] = (
            "Найдено много вариантов. "
            "Кратко перечисли их и уточни, "
            "что именно интересует пользователя."
        )

    return result


# ---------------------------------------------------------------------------
# Вспомогательная фильтрация
# ---------------------------------------------------------------------------

def _filter_by_query(
    products: list[dict],
    query: str
) -> list[dict]:

    if not query:
        return products

    # Прямой поиск по исходному запросу.
    # Нужен для названий брендов и платёжных систем:
    # Элкарт, Visa, Mastercard и т.д.
    raw_query = query.strip().lower()

    if raw_query:
        direct_result = [
            p
            for p in products
            if raw_query in _product_text(p).lower()
        ]

        if direct_result:
            return direct_result

    # Старый механизм нормализации и стемминга
    # оставляем для обычных слов.
    normalized_query = _norm(query)

    stems = [
        _stem(token).lower()
        for token in _tokens(normalized_query)
    ]

    if not stems:
        return products

    return [
        p
        for p in products
        if any(
            stem in _product_text(p).lower()
            for stem in stems
        )
    ]


# ---------------------------------------------------------------------------
# Карты
# ---------------------------------------------------------------------------

def list_card_products(
    query: str = ""
) -> list[dict]:
    """
    Основной инструмент для любых вопросов о банковских картах.

    Возвращает компактную информацию:
    - название;
    - категорию;
    - платёжную систему;
    - валюты;
    - стоимость выпуска;
    - стоимость годового обслуживания.

    Для пустого query возвращаются карты для физических лиц.

    Бизнес-карты показываются только если пользователь
    явно спрашивает о бизнес-картах.
    """

    products = _get_cards_from_db()

    normalized_query = _norm(query)

    business_words = (
        "бизнес",
        "ип",
        "юридичес",
        "предпринимател",
    )

    is_business_query = any(
        word in normalized_query
        for word in business_words
    )

    # Обычный запрос относится к физическому лицу.
    # Поэтому бизнес-карты не показываем.
    if not is_business_query:
        products = [
            p
            for p in products
            if (p.get("category") or {}).get("name") != "Бизнес"
        ]

    # Сначала фильтруем полные данные из БД,
    # чтобы поиск работал по всем доступным полям.
    products = _filter_by_query(
        products,
        query
    )

    # В LLM отправляем только необходимые данные.
    return [
        _compact(product, "cards")
        for product in products
    ]


# ---------------------------------------------------------------------------
# Кредиты
# ---------------------------------------------------------------------------

def list_credit_products(
    query: str = ""
) -> list[dict]:
    """
    Список кредитных продуктов банка.

    query:
    необязательный фильтр,
    например "авто", "ипотека".
    """

    return _filter_by_query(
        eldik_client.get_credits(),
        query
    )


# ---------------------------------------------------------------------------
# Депозиты
# ---------------------------------------------------------------------------

def list_deposit_products(
    query: str = ""
) -> list[dict]:
    """
    Список депозитных продуктов банка.
    """

    return _filter_by_query(
        eldik_client.get_deposits(),
        query
    )


# ---------------------------------------------------------------------------
# Тарифы
# ---------------------------------------------------------------------------

def get_tariff_documents(
    query: str = ""
) -> list[dict]:
    """
    Официальные документы с тарифами банка.

    Используются, когда стоимость обслуживания
    или выпуска не указана в карточке продукта.
    """

    docs = eldik_client.get_tariff_documents()

    if not query:
        return docs

    stems = [
        _stem(t)
        for t in _tokens(query)
    ]

    if not stems:
        return docs

    filtered = [
        d
        for d in docs
        if all(
            s in _norm(d["title"])
            for s in stems
        )
    ]

    if filtered:
        return filtered

    return [
        d
        for d in docs
        if any(
            s in _norm(d["title"])
            for s in stems
        )
    ]


# ---------------------------------------------------------------------------
# Контакты
# ---------------------------------------------------------------------------

def get_bank_contacts() -> dict:
    """
    Контакты банка.
    """

    return eldik_client.BANK_CONTACTS


# ---------------------------------------------------------------------------
# Курсы валют
# ---------------------------------------------------------------------------

def get_exchange_rate(
    currency: str = ""
) -> dict:
    """
    Актуальные курсы валют банка.

    currency:
    USD, EUR, RUB, KZT, CNY, TRY, AED, GBP.

    Пусто = все валюты.
    """

    rates = eldik_client.get_exchange_rates()

    if not currency:
        return rates

    currency = currency.upper()

    cash = next(
        (
            r
            for r in rates["cash"]
            if r["currency"] == currency
        ),
        None
    )

    cashless = next(
        (
            r
            for r in rates["cashless"]
            if r["currency"] == currency
        ),
        None
    )

    if not cash and not cashless:

        return {
            "error": (
                f"Валюта {currency} "
                "не найдена в списке банка"
            )
        }

    return {
        "date": rates["date"],
        "currency": currency,
        "cash": cash,
        "cashless": cashless,
        "note": rates["note"],
    }


# ---------------------------------------------------------------------------
# Расчёт кредита
# ---------------------------------------------------------------------------

def calculate_loan_payment(
    amount: float,
    annual_rate_percent: float,
    term_months: int
) -> dict:
    """
    Ежемесячный аннуитетный платёж.

    Ставку для конкретного продукта
    сначала нужно узнать через list_credit_products.
    """

    if amount <= 0 or term_months <= 0:

        return {
            "error": (
                "Сумма и срок должны "
                "быть положительными числами"
            )
        }

    monthly_rate = (
        annual_rate_percent
        / 100
        / 12
    )

    if monthly_rate == 0:

        monthly_payment = (
            amount
            / term_months
        )

    else:

        factor = (
            (1 + monthly_rate)
            ** term_months
        )

        monthly_payment = (
            amount
            * monthly_rate
            * factor
            / (factor - 1)
        )

    total_payment = (
        monthly_payment
        * term_months
    )

    return {
        "monthly_payment": round(
            monthly_payment,
            2
        ),

        "total_payment": round(
            total_payment,
            2
        ),

        "overpayment": round(
            total_payment - amount,
            2
        ),

        "amount": amount,

        "annual_rate_percent":
            annual_rate_percent,

        "term_months":
            term_months,

        "note": (
            "Ориентировочный расчёт "
            "(аннуитет), реальный график "
            "банка может отличаться"
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
    """
    Доход по депозиту.
    Простые проценты без капитализации.
    """

    if amount <= 0 or term_months <= 0:

        return {
            "error": (
                "Сумма и срок должны "
                "быть положительными числами"
            )
        }

    total_interest = (
        amount
        * (annual_rate_percent / 100)
        * (term_months / 12)
    )

    return {
        "initial_amount": amount,

        "total_interest": round(
            total_interest,
            2
        ),

        "total_payout": round(
            amount + total_interest,
            2
        ),

        "annual_rate_percent":
            annual_rate_percent,

        "term_months":
            term_months,

        "note": (
            "Ориентировочный расчёт "
            "без капитализации, условия "
            "конкретного продукта могут отличаться"
        ),
    }


# ---------------------------------------------------------------------------
# Описания функций для LLM
# ---------------------------------------------------------------------------

_QUERY_PARAM = {
    "type": "string",
    "description": (
        "Необязательный текстовый фильтр"
    ),
}


TOOL_DECLARATIONS = [

    # ---------------------------------------------------------
    # Универсальный поиск
    # ---------------------------------------------------------

    {
        "name": "search_bank_products",

        "description": (
            "Получает актуальные курсы валют Элдик Банка "
            "(наличный и безналичный курс) с датой обновления. "
            "Если пользователь спрашивает курс одной валюты, "
            "передай её код в currency, например USD или RUB. "
            "Если пользователь спрашивает две или более валют, "
            "вызывай инструмент ОДИН РАЗ с пустым currency, "
            "чтобы получить курсы всех валют сразу. "
            "Не вызывай инструмент повторно, если полученных "
            "данных достаточно для ответа." 
        ),

        "parameters": {
            "type": "object",

            "properties": {
                "query": {
                    "type": "string",

                    "description": (
                        "Запрос пользователя "
                        "как есть"
                    ),
                },
            },

            "required": [
                "query"
            ],
        },
    },

    # ---------------------------------------------------------
    # Карты
    # ---------------------------------------------------------

    {
        "name": "list_card_products",

        "description": (
            "ОСНОВНОЙ инструмент для любых вопросов "
            "о банковских картах. "
            "Используй для запросов: какие карты есть, "
            "список карт, стоимость карты, стоимость выпуска, "
            "стоимость обслуживания, Visa, Mastercard, Элкарт, "
            "виртуальные, дебетовые, премиальные, пенсионные "
            "и другие карты. "
            "Пустой query возвращает все карты "
            "для физических лиц."
        ),

        "parameters": {

            "type": "object",

            "properties": {
                "query": _QUERY_PARAM,
            },
        },
    },

    # ---------------------------------------------------------
    # Кредиты
    # ---------------------------------------------------------

    {
        "name": "list_credit_products",

        "description": (
            "Основной инструмент для вопросов "
            "о кредитах и кредитных продуктах банка. "
            "Возвращает сумму, срок, ставку "
            "и другие условия."
        ),

        "parameters": {

            "type": "object",

            "properties": {
                "query": _QUERY_PARAM,
            },
        },
    },

    # ---------------------------------------------------------
    # Депозиты
    # ---------------------------------------------------------

    {
        "name": "list_deposit_products",

        "description": (
            "Основной инструмент для вопросов "
            "о депозитах и вкладах банка. "
            "Возвращает ставку, срок, минимальную сумму "
            "и другие условия."
        ),

        "parameters": {

            "type": "object",

            "properties": {
                "query": _QUERY_PARAM,
            },
        },
    },

    # ---------------------------------------------------------
    # Тарифы
    # ---------------------------------------------------------

    {
        "name": "get_tariff_documents",

        "description": (
            "Официальные документы с тарифами банка. "
            "Используй, если пользователь спрашивает "
            "конкретный тариф, а стоимость выпуска "
            "или обслуживания отсутствует в данных продукта."
        ),

        "parameters": {

            "type": "object",

            "properties": {
                "query": _QUERY_PARAM,
            },
        },
    },

    # ---------------------------------------------------------
    # Контакты
    # ---------------------------------------------------------

    {
        "name": "get_bank_contacts",

        "description": (
            "Контакты банка. Используй ТОЛЬКО если пользователь "
            "прямо спрашивает номер телефона, адрес, WhatsApp, "
            "email или как связаться с банком. "
            "Не используй для отсутствующих или неуказанных "
            "данных о продуктах."
        ),

        "parameters": {
            "type": "object",

            "properties": {},
        },
    },

    # ---------------------------------------------------------
    # Курсы валют
    # ---------------------------------------------------------

    {
        "name": "get_exchange_rate",

        "description": (
            "Актуальный курс валют банка "
            "(наличный и безналичный)."
        ),

        "parameters": {

            "type": "object",

            "properties": {

                "currency": {

                    "type": "string",

                    "description": (
                        "Код валюты: "
                        "USD, EUR, RUB, KZT, "
                        "CNY, TRY, AED, GBP. "
                        "Пусто = все валюты."
                    ),
                },
            },
        },
    },

    # ---------------------------------------------------------
    # Калькулятор кредита
    # ---------------------------------------------------------

    {
        "name": "calculate_loan_payment",

        "description": (
            "Рассчитать ежемесячный платёж "
            "по кредиту (аннуитет)."
        ),

        "parameters": {

            "type": "object",

            "properties": {

                "amount": {
                    "type": "number",

                    "description": (
                        "Сумма кредита в сомах"
                    ),
                },

                "annual_rate_percent": {
                    "type": "number",

                    "description": (
                        "Годовая ставка "
                        "в процентах, например 20"
                    ),
                },

                "term_months": {
                    "type": "integer",

                    "description": (
                        "Срок кредита в месяцах"
                    ),
                },
            },

            "required": [
                "amount",
                "annual_rate_percent",
                "term_months",
            ],
        },
    },

    # ---------------------------------------------------------
    # Калькулятор депозита
    # ---------------------------------------------------------

    {
        "name": "calculate_deposit_income",

        "description": (
            "Рассчитать доход по депозиту."
        ),

        "parameters": {

            "type": "object",

            "properties": {

                "amount": {
                    "type": "number",

                    "description": (
                        "Сумма вклада в сомах"
                    ),
                },

                "annual_rate_percent": {
                    "type": "number",

                    "description": (
                        "Годовая ставка "
                        "в процентах, например 12"
                    ),
                },

                "term_months": {
                    "type": "integer",

                    "description": (
                        "Срок вклада в месяцах"
                    ),
                },
            },

            "required": [
                "amount",
                "annual_rate_percent",
                "term_months",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Реестр функций
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {

    "search_bank_products":
        search_bank_products,

    "list_card_products":
        list_card_products,

    "list_credit_products":
        list_credit_products,

    "list_deposit_products":
        list_deposit_products,

    "get_tariff_documents":
        get_tariff_documents,

    "get_bank_contacts":
        get_bank_contacts,

    "get_exchange_rate":
        get_exchange_rate,

    "calculate_loan_payment":
        calculate_loan_payment,

    "calculate_deposit_income":
        calculate_deposit_income,
}
# ---------------------------------------------------------------------------
# Получение карт из базы данных
# ---------------------------------------------------------------------------

def _get_cards_from_db() -> list[dict]:
    """
    Получает карты из PostgreSQL в формате,
    совместимом с существующим кодом tools.py.
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.id,
                    c.eldik_id,
                    c.slug,
                    c.name,
                    c.short_desc,
                    c.issuance,
                    c.annual_service,
                    c.account_opening,
                    c.image,
                    c.image_mob,
                    c.is_creatable,
                    c.is_available,
                    c.card_expiration_date,

                    cc.id AS category_id,
                    cc.name AS category_name,

                    ps.id AS payment_system_id,
                    ps.name AS payment_system_name,
                    ps.image AS payment_system_image,
                    ps.is_available AS payment_system_available,
                    ps.is_open AS payment_system_open,
                    ps.is_active AS payment_system_active

                FROM cards c

                LEFT JOIN card_categories cc
                    ON c.category_id = cc.id

                LEFT JOIN payment_systems ps
                    ON c.payment_system_id = ps.id

                ORDER BY c.id
                """
            )

            rows = cur.fetchall()

            cards = []

            for row in rows:
                (
                    card_id,
                    eldik_id,
                    slug,
                    name,
                    short_desc,
                    issuance,
                    annual_service,
                    account_opening,
                    image,
                    image_mob,
                    is_creatable,
                    is_available,
                    card_expiration_date,
                    category_id,
                    category_name,
                    payment_system_id,
                    payment_system_name,
                    payment_system_image,
                    payment_system_available,
                    payment_system_open,
                    payment_system_active,
                ) = row

                cur.execute(
                    """
                    SELECT
                        cu.id,
                        cu.name,
                        cu.code
                    FROM card_currencies ccur
                    JOIN currencies cu
                        ON ccur.currency_id = cu.id
                    WHERE ccur.card_id = %s
                    ORDER BY cu.code
                    """,
                    (card_id,),
                )

                currencies = [
                    {
                        "id": currency_id,
                        "name": currency_name,
                        "code": currency_code,
                    }
                    for currency_id, currency_name, currency_code
                    in cur.fetchall()
                ]

                cards.append(
                    {
                        "id": eldik_id,
                        "slug": slug,
                        "name": name,
                        "short_desc": short_desc,
                        "issuance": issuance,
                        "annual_service": annual_service,
                        "account_opening": account_opening,
                        "image": image,
                        "image_mob": image_mob,
                        "is_creatable": is_creatable,
                        "is_available": is_available,
                        "card_expiration_date": card_expiration_date,
                        "category": {
                            "id": category_id,
                            "name": category_name,
                        }
                        if category_id is not None
                        else None,
                        "payment_system": {
                            "id": payment_system_id,
                            "name": payment_system_name,
                            "image": payment_system_image,
                            "is_available": payment_system_available,
                            "is_open": payment_system_open,
                            "is_active": payment_system_active,
                        }
                        if payment_system_id is not None
                        else None,
                        "currencies": currencies,
                    }
                )

            return cards