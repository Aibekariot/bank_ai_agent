"""
Клиент для получения данных с публичного сайта Элдик Банка (eldik.kg).

ВАЖНО: используется незадокументированный внутренний JSON API сайта
(обнаружен через DevTools -> Network -> Fetch/XHR), а не официальный
партнёрский API банка. Для демо это ок, но перед реальным использованием
нужно согласовать доступ с банком.

Эндпоинты вида /_next/data/{BUILD_ID}/ru/{page}.json зависят от build id
сборки Next.js-сайта. Он меняется при пересборке сайта банком, поэтому
build id берётся из HTML страницы и обновляется автоматически при 404.
"""

import os
import re
import time

import httpx

BASE_URL = "https://eldik.kg"

# Можно задать переменной окружения; иначе узнаём со страницы сайта.
_build_id: str | None = os.environ.get("ELDIK_BUILD_ID") or None

_BUILD_ID_RE = re.compile(r'"buildId"\s*:\s*"([^"]+)"')

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


def _fetch_build_id(page: str) -> str:
    """Build id текущей сборки сайта из __NEXT_DATA__ обычной HTML-страницы."""
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        response = client.get(f"{BASE_URL}/ru/{page}", headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    match = _BUILD_ID_RE.search(response.text)
    if not match:
        raise RuntimeError("build id сайта не найден на странице")
    print(f"[HTTP] build id сайта: {match.group(1)}")
    return match.group(1)


def _get_next_data(page: str) -> dict:
    """JSON страницы Next.js. При 404 (сайт пересобран) build id обновляется один раз."""
    global _build_id
    if not _build_id:
        _build_id = _fetch_build_id(page)
    try:
        return _cached_get(f"{BASE_URL}/_next/data/{_build_id}/ru/{page}.json")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        _build_id = _fetch_build_id(page)
        return _cached_get(f"{BASE_URL}/_next/data/{_build_id}/ru/{page}.json")


def get_exchange_rates() -> dict:
    """Текущие курсы валют банка: наличные, безналичные, золото."""
    data = _get_next_data("archive-currency")
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
