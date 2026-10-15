"""
knowledge.py - единственная точка доступа агента к базе знаний банка.

Данные лежат в backend/knowledge/*.json и создаются скриптом
scripts/build_knowledge.py из сырых файлов сайта. Модуль:

  * один раз (лениво, при первом обращении) читает эти файлы в память;
  * умеет искать документы по словам запроса;
  * НЕ ходит в интернет и НЕ обращается к базе данных.

Весь остальной код (tools.py) работает с данными только через этот модуль.
Если позже понадобится PostgreSQL или другой источник, меняется только
этот файл, а tools.py остаётся прежним.

Юридические тексты (раздел "legal": оферта, политика конфиденциальности)
в поиск не попадают: они большие и не нужны для ответов клиентам.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

DEFAULT_DIR = Path(
    os.environ.get("KNOWLEDGE_DIR")
    or Path(__file__).resolve().parent / "knowledge"
)

# Разделы, которые не участвуют в поиске.
EXCLUDED_SECTIONS = {"legal"}


class KnowledgeError(RuntimeError):
    """База знаний не найдена или повреждена."""


# ---------------------------------------------------------------------------
# Нормализация текста для поиска
# ---------------------------------------------------------------------------

# Кириллические буквы-двойники приводим к латинице и в запросе, и в тексте,
# поэтому "Masterсard" с русской "с" всё равно находится.
_HOMOGLYPHS = str.maketrans("аеорсухкмтнв", "aeopcyxkmthb")


def norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е").translate(_HOMOGLYPHS)


_STOPWORDS = {
    norm(w)
    for w in [
        "и", "в", "на", "по", "что", "как", "мне", "про", "для", "или",
        "это", "есть", "какой", "какая", "какие", "какое", "сколько",
        "стоит", "хочу", "расскажи", "расскажите", "можно", "банк",
        "банка", "элдик", "eldik", "у", "вас", "вы", "а", "о", "об", "с",
        "со", "мой", "моя", "нужен", "нужна", "нужно", "подскажите",
        "пожалуйста", "информация", "инфо", "где", "чем", "почему",
        "за", "из", "до", "от", "при", "без", "над", "под", "не", "но",
        "ли", "же", "бы", "мои", "меня", "если",
    ]
}

_SYNONYMS = {
    norm(k): norm(v)
    for k, v in {
        "элкард": "элкарт",
        "elcard": "элкарт",
        "elkart": "элкарт",
        "эл-карт": "элкарт",
        "мастеркард": "mastercard",
        "мастер": "mastercard",
        "виза": "visa",
        "вклад": "депозит",
        "вклады": "депозит",
        "вкладе": "депозит",
        "вклада": "депозит",
        "вкладов": "депозит",
        "детей": "детский",
        "дети": "детский",
        "детям": "детский",
        "детская": "детский",
        "детское": "детский",
        "ребенок": "детский",
        "ребенка": "детский",
        "приложение": "мобильный",
        "приложении": "мобильный",
        "приложения": "мобильный",
    }.items()
}

# Слова-названия разделов. Они не помогают выбрать продукт внутри раздела
# ("карты", "кредиты"), поэтому в конкретном разделе их отбрасываем.
SECTION_GENERIC_STEMS = {
    section: tuple(norm(w) for w in words)
    for section, words in {
        "cards": ("карт", "card"),
        "credits": ("креди", "займ", "ссуд"),
        "deposits": ("депоз", "накоп", "сбере"),
    }.items()
}


# Слова, по которым понятно, что вопрос относится к разделу целиком.
# Если слово запроса начинается с такой основы, документы этого раздела
# получают бонус, даже когда само слово в их тексте не встретилось.
SECTION_HINT_STEMS = {
    section: tuple(norm(w) for w in words)
    for section, words in {
        "transfers": ("перевод", "перевес", "transfer"),
        "mobile_banking": ("мобильн", "банкинг", "приложен"),
        "accounts": ("счет", "счёт"),
        "islamic": ("исламск", "мурабах", "ислам"),
        "overdraft": ("овердрафт",),
        "salary_project": ("зарплат",),
        "tariffs": ("тариф",),
        "instructions": ("пин", "смен", "инструкц"),
        "card_privileges": ("привилег", "лаунж", "lounge", "fast", "кешб", "кэшб", "cashback",
                            "роуминг", "flexi", "страхов"),
    }.items()
}


# Узкие разделы: подробности привилегий отдельных карт. Они не должны
# попадать в ответ на посторонние запросы ("перевод за границу"), поэтому при
# поиске без указания раздела берутся, только если в запросе есть слово
# из этого списка. Указав section явно, можно искать в них всегда.
NARROW_SECTION_TRIGGERS = {
    "card_privileges": tuple(norm(w) for w in (
        "привилег", "лаунж", "lounge", "fast", "фаст", "кешб", "кэшб", "cashback",
        "роуминг", "flexi", "флекс", "страхов", "elite", "элит", "world", "travel",
        "dragon", "драгон", "консьерж", "concierge", "манас", "vip", "вип", "esim",
        "airalo", "ячейк", "персональн",
    )),
}
_NARROW_EXACT = {"card_privileges": {norm(w) for w in ("зал", "залы", "залов", "зале", "залах", "залом")}}


def _narrow_allowed(section: str, stems: list[str]) -> bool:
    triggers = NARROW_SECTION_TRIGGERS.get(section)
    if triggers is None:
        return True
    exact = _NARROW_EXACT.get(section, set())
    return any(s in exact or any(s.startswith(t[:5]) for t in triggers) for s in stems)


def stem(token: str) -> str:
    """Грубая основа слова: первые 5 букв (кредиты/кредитов -> креди)."""
    return token[:5] if len(token) >= 5 else token


def query_stems(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9а-я]+", norm(query))
    result = []
    for word in words:
        word = _SYNONYMS.get(word, word)
        if word in _STOPWORDS or len(word) < 2:
            continue
        result.append(stem(word))
    # убираем повторы, сохраняя порядок
    return list(dict.fromkeys(result))


def drop_generic(stems: list[str], section: str) -> list[str]:
    generic = SECTION_GENERIC_STEMS.get(section, ())
    return [s for s in stems if not any(s.startswith(g) for g in generic)]


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------

class _Store:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.manifest: dict = {}
        self.locations: list[dict] = []
        self.directory: Path | None = None
        self._index: dict[str, dict] = {}


_lock = threading.Lock()
_store: _Store | None = None


def _index_doc(doc: dict) -> dict:
    title = norm(doc.get("title", ""))
    conditions = " ".join(
        f"{c.get('key', '')} {c.get('value', '')}" for c in doc.get("conditions", [])
    )
    attrs = " ".join(
        str(v) for v in doc.get("attributes", {}).values()
        if isinstance(v, (str, int)) and not isinstance(v, bool)
    )
    body = norm(f"{doc.get('text', '')} {conditions} {attrs} {doc.get('slug', '')}")
    return {"title": title, "body": body}


def load(directory: Path | str | None = None) -> _Store:
    """Читает все *.json из папки базы знаний. Вызывается автоматически."""
    global _store
    path = Path(directory) if directory else DEFAULT_DIR

    if not path.is_dir():
        raise KnowledgeError(
            f"Папка базы знаний не найдена: {path}. "
            f"Запустите: python scripts/build_knowledge.py"
        )

    store = _Store()
    store.directory = path

    manifest_path = path / "_manifest.json"
    if manifest_path.exists():
        store.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for file in sorted(path.glob("*.json")):
        if file.name.startswith("_"):
            continue
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KnowledgeError(f"Повреждён файл {file.name}: {exc}") from exc
        if file.stem == "locations":
            store.locations = payload.get("items", [])
            continue
        for doc in payload.get("documents", []):
            if doc["id"] in store.by_id:
                raise KnowledgeError(f"Дублирующийся id документа: {doc['id']}")
            store.docs.append(doc)
            store.by_id[doc["id"]] = doc
            store._index[doc["id"]] = _index_doc(doc)

    if not store.docs:
        raise KnowledgeError(f"В {path} нет документов. Запустите build_knowledge.py")

    _store = store
    return store


def _get_store() -> _Store:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                load()
    return _store  # type: ignore[return-value]


def reload(directory: Path | str | None = None) -> None:
    """Перечитать файлы без перезапуска сервера (после обновления данных)."""
    with _lock:
        load(directory)


def status() -> dict:
    """Краткая сводка для /health и логов."""
    store = _get_store()
    sections: dict[str, int] = {}
    for doc in store.docs:
        sections[doc["section"]] = sections.get(doc["section"], 0) + 1
    return {
        "directory": str(store.directory),
        "documents": len(store.docs),
        "sections": sections,
        "data_date": store.manifest.get("data_date"),
    }


# ---------------------------------------------------------------------------
# Доступ и поиск
# ---------------------------------------------------------------------------

def section_docs(section: str) -> list[dict]:
    return [d for d in _get_store().docs if d["section"] == section]


def get_doc(doc_id: str) -> dict | None:
    return _get_store().by_id.get(doc_id)


def _score(doc: dict, stems: list[str]) -> tuple[int, int]:
    """
    (сколько слов запроса найдено, суммарный вес).
    Заголовок весит больше текста; слово-подсказка раздела даёт бонус.
    """
    index = _get_store()._index[doc["id"]]
    hints = SECTION_HINT_STEMS.get(doc["section"], ())
    matched = weight = 0
    for s in stems:
        hit = False
        if s in index["title"]:
            hit, weight = True, weight + 3
        elif s in index["body"]:
            hit, weight = True, weight + 1
        if hints and any(s.startswith(h[:5]) for h in hints):
            hit, weight = True, weight + 2
        if hit:
            matched += 1
    return matched, weight


# Документ попадает в ответ, если его вес не меньше этой доли от лучшего.
# 0.6: "visa gold" оставляет только Visa Gold (вес 6), а не все Visa (вес 3).
MIN_WEIGHT_SHARE = 0.6


def _pick_best(scored: list[tuple[int, dict]]) -> list[dict]:
    """scored: [(вес, документ)] -> лучшие документы по убыванию веса."""
    if not scored:
        return []
    best = max(w for w, _ in scored)
    kept = [(w, d) for w, d in scored if w >= best * MIN_WEIGHT_SHARE]
    kept.sort(key=lambda x: -x[0])
    return [d for _, d in kept]


def search(
    query: str,
    sections: list[str] | None = None,
    limit: int = 5,
    drop_section_words: bool = True,
) -> list[dict]:
    """
    Поиск документов по запросу.

    Возвращает документы, в которых нашлось максимальное для этого запроса
    число слов. Если слов для поиска не осталось (запрос из одних общих слов
    вроде "карты"), возвращает пустой список: решение, что показать,
    принимает вызывающий код.
    """
    stems = query_stems(query)
    if not stems:
        return []

    pool = [
        d for d in _get_store().docs
        if d["section"] not in EXCLUDED_SECTIONS
        and (d["section"] in sections if sections else _narrow_allowed(d["section"], stems))
    ]

    scored = []
    for doc in pool:
        doc_stems = (
            drop_generic(stems, doc["section"]) if drop_section_words else stems
        )
        if not doc_stems:
            # Запрос состоит только из названия этого раздела ("вклад").
            scored.append((100, doc))
            continue
        matched, weight = _score(doc, doc_stems)
        if matched:
            scored.append((weight, doc))

    return _pick_best(scored)[:limit]


def filter_section(section: str, query: str = "") -> tuple[list[dict], bool]:
    """
    Документы раздела, подходящие под запрос.

    Возвращает (документы, был_ли_применён_фильтр).
    Пустой запрос или запрос из одних общих слов возвращает весь раздел.
    """
    docs = section_docs(section)
    stems = drop_generic(query_stems(query), section)
    if not stems:
        return docs, False

    scored = []
    for doc in docs:
        matched, weight = _score(doc, stems)
        if matched:
            scored.append((weight, doc))

    return _pick_best(scored), True


# ---------------------------------------------------------------------------
# Точки обслуживания (банкоматы, филиалы, кассы)
# ---------------------------------------------------------------------------

LOCATION_KINDS = ("atm", "branch", "savings_cash", "mobile_cash", "other")

# Слова запроса, которые описывают тип точки, а не место.
_LOCATION_NOISE = (
    "банкомат", "атм", "atm", "отделен", "филиал", "касс", "сберкасс",
    "ближайш", "рядом", "где", "найд", "адрес", "есть", "наход", "располож",
    "сберегат", "выездн", "точк", "банк", "элдик", "eldik",
)

def find_locations(query: str = "", kind: str = "", limit: int = 8) -> dict:
    """
    Точки обслуживания по тексту запроса (город, улица, область) и типу.

    Возвращает также coverage: в каких регионах вообще есть такие точки,
    чтобы агент мог честно сказать "в моих данных нет банкоматов в Оше".
    """
    store = _get_store()
    items = store.locations
    if kind in LOCATION_KINDS:
        items = [i for i in items if i["kind"] == kind]

    coverage: dict[str, int] = {}
    for item in items:
        key = item.get("region") or "не указан"
        coverage[key] = coverage.get(key, 0) + 1

    stems = [
        s for s in query_stems(query or "")
        if not any(s.startswith(n[:5]) for n in _LOCATION_NOISE)
    ]

    if stems:
        scored = []
        for item in items:
            haystack = norm(" ".join(
                str(item.get(f) or "") for f in ("name", "address", "city", "region")
            ))
            padded = f" {haystack}"
            hits = sum(1 for s in stems if f" {s}" in padded)
            if hits:
                scored.append((hits, item))
        scored.sort(key=lambda x: -x[0])
        best = scored[0][0] if scored else 0
        found = [i for h, i in scored if h == best]
    else:
        found = list(items)

    return {
        "total": len(found),
        "items": found[:limit],
        "coverage": coverage,
        "data_date": store.manifest.get("data_date"),
    }
