"""
Клиент для получения данных с публичного сайта Элдик Банка (eldik.kg).

ВАЖНО: используется незадокументированный внутренний JSON API сайта
(обнаружен через DevTools -> Network -> Fetch/XHR), а не официальный
партнёрский API банка. Для демо это ок, но перед реальным использованием
нужно согласовать доступ с банком.

Эндпоинты вида /_next/data/{BUILD_ID}/ru/{page}.json зависят от build id
сборки Next.js-сайта. Он меняется при пересборке сайта банком. Если
запросы начнут возвращать 404 - обновить BUILD_ID (см. README).
"""

import html
import os
import re
import time

import httpx

BASE_URL = "https://eldik.kg"

# Можно переопределить переменной окружения, не трогая код.
BUILD_ID = os.environ.get("ELDIK_BUILD_ID", "ghL1BB5osN958Z-ryfzkV")

_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SECONDS = 15 * 60  # 15 минут

# Контакты взяты из /api/site_settings/with_footer_header (публичные данные сайта).
BANK_CONTACTS = {
    "contact_center": "9111 (круглосуточно, 24/7)",
    "phone": "+996 (312) 91 11 11",
    "trust_phone": "+996 (312) 35-55-55",
    "whatsapp": "+996 (706) 911 111",
    "email": "info@eldik.kg",
    "head_office_address": "г. Бишкек, ул. Киевская, 76",
    "website": "https://eldik.kg",
    "mobile_app": {
        "google_play": "https://play.google.com/store/apps/details?id=kg.rsk.staging&hl=en",
        "app_store": "https://apps.apple.com/kg/app/eldik/id6596756225",
    },
    "credit_department_individuals": "(0312) 58-01-47",
    "credit_department_legal": "(0312) 58-01-19",
    "license": "Лицензия НБКР №033 от 05.06.2024",
}


def _clean_html(raw: str | None) -> str:
    """Убирает HTML-теги и entities из описаний, схлопывает пробелы."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _cached_get(url: str) -> dict:
    """
    GET-запрос к Eldik с кэшированием.

    Показывает в логах:
    - CACHE HIT
    - CACHE MISS
    - CACHE EXPIRED
    - фактическое время HTTP-запроса
    """

    now = time.time()

    # =========================================================
    # Проверяем кэш
    # =========================================================

    if url in _cache:

        cached_at, data = _cache[url]

        age = now - cached_at

        if age < CACHE_TTL_SECONDS:

            print(
                f"[CACHE] HIT | "
                f"age={age:.2f}s | "
                f"url={url}"
            )

            return data

        print(
            f"[CACHE] EXPIRED | "
            f"age={age:.2f}s | "
            f"url={url}"
        )

    # =========================================================
    # Кэша нет
    # =========================================================

    print(
        f"[CACHE] MISS | "
        f"url={url}"
    )

    started = time.perf_counter()

    try:

        with httpx.Client(
            timeout=10.0
        ) as client:

            response = client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
            )

            response.raise_for_status()

            data = response.json()

    except Exception as exc:

        elapsed = (
            time.perf_counter()
            - started
        )

        print(
            f"[HTTP] ERROR | "
            f"time={elapsed:.3f}s | "
            f"url={url} | "
            f"error={exc}"
        )

        raise

    elapsed = (
        time.perf_counter()
        - started
    )

    print(
        f"[HTTP] GET | "
        f"time={elapsed:.3f}s | "
        f"url={url}"
    )

    # =========================================================
    # Сохраняем результат
    # =========================================================

    _cache[url] = (
        time.time(),
        data,
    )

    print(
        f"[CACHE] SAVED | "
        f"ttl={CACHE_TTL_SECONDS}s"
    )

    return data


def _next_data_url(page: str) -> str:
    return f"{BASE_URL}/_next/data/{BUILD_ID}/ru/{page}.json"


def get_exchange_rates() -> dict:
    """Текущие курсы валют банка: наличные, безналичные, золото."""
    data = _cached_get(_next_data_url("archive-currency"))
    page_data = data["pageProps"]["data"]
    date = data["pageProps"].get("chech", {}).get("date", "")

    def _simplify(entries: list[dict]) -> list[dict]:
        return [
            {
                "currency": e["currency"]["code"],
                "buy": float(e["buy"]),
                "sell": float(e["sell"]),
                "commission_percent": float(e["commission"]) if e.get("commission") is not None else None,
                "nbkr_rate": float(e["nbkr"]) if e.get("nbkr") is not None else None,
            }
            for e in entries
        ]

    return {
        "date": date,
        "note": "Курсы действуют для головного отделения; в других отделениях могут отличаться. "
        "При конвертации свыше 1000 USD могут действовать договорные курсы.",
        "cash": _simplify(page_data.get("cash_exchanges", [])),
        "cashless": _simplify(page_data.get("cashless_exchanges", [])),
        "gold": page_data.get("gold_exchanges", []),
    }


def get_credits() -> list[dict]:
    """Кредитные продукты для физлиц."""
    data = _cached_get(_next_data_url("credits"))
    results = data["pageProps"]["creditsList"]["results"]

    return [
        {
            "name": item["name"],
            "slug": item["slug"],
            "description": _clean_html(item.get("short_desc")),
            "conditions": {s["key"]: s["value"] for s in item.get("shorts", [])},
        }
        for item in results
    ]


def get_deposits() -> list[dict]:
    """
    Депозитные продукты для физлиц.

    ВНИМАНИЕ: у некоторых депозитов is_available=True, но в описании написано
    "Недоступен для новых клиентов" / "Временно недоступен для открытия".
    Поэтому описание обязательно передаём агенту.
    """
    data = _cached_get(_next_data_url("depozits"))
    results = data["pageProps"]["data"]["deposits"]

    return [
        {
            "name": item["name"],
            "slug": item["slug"],
            "description": _clean_html(item.get("short_desc")),
            "conditions": {s["key"]: s["value"] for s in item.get("shorts", [])},
        }
        for item in results
    ]


def get_cards() -> list[dict]:
    """Платёжные карты банка (дебетовые, премиум, виртуальные, бизнес)."""
    data = _cached_get(_next_data_url("payment-cards"))
    results = data["pageProps"]["data"]["results"]

    return [
        {
            "name": c["name"],
            "slug": c["slug"],
            "description": _clean_html(c.get("short_desc")),
            "category": (c.get("category") or {}).get("name"),
            "payment_system": (c.get("payment_system") or {}).get("name"),
            "currencies": [cur["name"] for cur in c.get("currencies", [])],
            # None означает "на странице сайта не указано" (тариф см. в PDF), а не "бесплатно"
            "issuance_cost": c.get("issuance"),
            "annual_service_cost": c.get("annual_service"),
            "validity": c.get("card_expiration_date"),
            "available": c.get("is_available", True),
            "online_order_available": c.get("is_creatable", False),
        }
        for c in results
    ]


def get_tariff_documents() -> list[dict]:
    """Список PDF-документов с тарифами (со всех страниц пагинации)."""
    url = f"{BASE_URL}/api/tariffs?for_who=individual&page=1&page_size=50"
    documents: list[dict] = []

    for _ in range(10):  # защита от бесконечного цикла
        data = _cached_get(url)
        documents.extend(
            {"title": item["title"], "file_url": item["file"]}
            for item in data.get("results", [])
        )
        next_url = data.get("next")
        if not next_url:
            break
        url = next_url

    return documents
