"""
Имитация API банка для демо-приложения (Flutter-приложение в корне репозитория).

Это НЕ часть агента. Настоящее приложение банка берёт курсы, адреса точек
и описания продуктов из своих систем. Демо-приложению их отдаёт этот модуль
из той же базы знаний, что и агенту, поэтому экраны и ответы агента совпадают.

Личных данных здесь нет: счета и карты тестового клиента вымышлены и лежат
в самом демо-приложении. Модуль можно удалить вместе с демо-приложением,
агент от него не зависит.
"""

from fastapi import APIRouter, HTTPException, Query

import eldik_client
import knowledge
import tools

router = APIRouter(prefix="/demo-bank/v1", tags=["demo-bank"])


@router.get("/rates")
def rates():
    """Курсы валют банка (живые данные сайта, как у инструмента агента)."""
    try:
        return eldik_client.get_exchange_rates()
    except Exception as exc:  # noqa: BLE001
        print(f"[DEMO-BANK] курсы недоступны: {exc}")
        raise HTTPException(status_code=503, detail="Курсы сейчас недоступны") from exc


@router.get("/locations")
def locations(
    query: str = "",
    kind: str = "",
    limit: int = Query(50, ge=1, le=300),
):
    """Банкоматы и отделения: тот же поиск, что у инструмента find_locations."""
    result = knowledge.find_locations(query, kind, limit=limit)
    return {
        "total": result["total"],
        "items": [tools._location_view(i) for i in result["items"]],
        "data_date": result["data_date"],
    }


def _card_summary(doc: dict) -> dict:
    attrs = doc.get("attributes", {})
    return {
        "slug": doc.get("slug"),
        "name": doc.get("title"),
        "category": attrs.get("category"),
        "payment_system": attrs.get("payment_system"),
        "issuance": attrs.get("issuance"),
        "annual_service": attrs.get("annual_service"),
    }


@router.get("/cards")
def cards():
    """Карты для физических лиц (бизнес-карты демо-приложению не нужны)."""
    docs = [
        d for d in knowledge.section_docs("cards")
        if d.get("attributes", {}).get("audience") != "business"
    ]
    return {"items": [_card_summary(d) for d in docs]}


@router.get("/cards/{slug}")
def card(slug: str):
    """Страница карты. null в полях значит "не указано", а не "бесплатно"."""
    doc = knowledge.get_doc(f"cards/{slug}")
    if doc is None:
        raise HTTPException(status_code=404, detail="Карта не найдена")
    attrs = doc.get("attributes", {})
    return {
        **_card_summary(doc),
        "currencies": attrs.get("currencies") or [],
        "card_expiration_date": attrs.get("card_expiration_date"),
        "details": doc.get("text", ""),
        "partial_data": doc.get("detail_level") == "list",
        "source_url": doc.get("source_url"),
        "data_date": doc.get("data_date"),
    }
