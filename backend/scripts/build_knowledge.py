"""
build_knowledge.py - превращает сырые JSON-файлы сайта eldik.kg
(папка jisonki_eldika) в компактную базу знаний backend/knowledge/.

Что делает:
  * выбрасывает служебные блоки Next.js (_nextI18Next - строки интерфейса,
    ~135 КБ в каждом файле), SEO-поля, картинки, баннеры;
  * переводит HTML в чистый текст (списки, таблицы, переносы строк);
  * склеивает карточку из списка карт с детальной страницей (если она есть);
  * исправляет буквы-двойники: кириллическая "с" внутри "Masterсard";
  * разделяет юридические тексты (оферта, политика) и обычные инструкции:
    юридические идут в legal.json и по умолчанию не должны попадать к модели;
  * печатает отчёт о покрытии: чего не хватает.

Что НЕ делает:
  * не удаляет и не изменяет исходные файлы;
  * не ходит в интернет (всё берётся из локальных файлов);
  * не придумывает данные: если поля нет, оно остаётся пустым.

Запуск (из папки backend):
    python scripts/build_knowledge.py
    python scripts/build_knowledge.py --data-date 2026-10-10

--data-date - дата, когда вы скачали данные с сайта. В самих файлах её нет,
поэтому по умолчанию берётся сегодняшняя дата. Лучше указывать настоящую.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = REPO_ROOT / "jisonki_eldika"
DEFAULT_OUT = REPO_ROOT / "backend" / "knowledge"

SITE = "https://eldik.kg"

# Адреса страниц выведены из имён эндпоинтов Next.js
# (например .../ru/payment-cards/visa-infinite.json -> /ru/payment-cards/visa-infinite).
# Для остальных разделов точный адрес страницы неизвестен, там стоит None.
# Перед показом откройте 2-3 ссылки в браузере и проверьте.
ITEM_URL = {
    "cards": SITE + "/ru/payment-cards/{slug}",
    "credits": SITE + "/ru/credits/{slug}",
}
SECTION_URL = {
    "cards": SITE + "/ru/payment-cards",
    "credits": SITE + "/ru/credits",
    "deposits": SITE + "/ru/depozits",
    "overdraft": SITE + "/ru/overdraft",
    "instructions": SITE + "/ru/cards/change-pin-code",
    "card_privileges": SITE + "/ru/payment-cards",
    "salary_project": SITE + "/ru/salary-project",
}

# Заголовки блоков, которые считаются юридическими текстами.
LEGAL_KEYWORDS = (
    "оферт",
    "политика конфиденциальности",
    "персонального характера",
    "правила использования цифровой подписи",
)


# ---------------------------------------------------------------------------
# HTML -> текст
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "p", "div", "section", "article", "ul", "ol", "table",
        "thead", "tbody", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._first_cell = True

    def _newline(self) -> None:
        self.parts.append("\n")

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "br" or tag in self.BLOCK_TAGS:
            self._newline()
        elif tag == "li":
            self._newline()
            self.parts.append("• ")
        elif tag == "tr":
            self._newline()
            self._first_cell = True
        elif tag in ("td", "th"):
            if not self._first_cell:
                self.parts.append(" | ")
            self._first_cell = False

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK_TAGS or tag in ("li", "tr"):
            self._newline()

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw) -> str:
    """HTML (или обычная строка) -> чистый текст без тегов и лишних пробелов."""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    if not raw.strip():
        return ""

    parser = _TextExtractor()
    parser.feed(raw)
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ")

    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        if not line or line == "•":
            continue
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Буквы-двойники (кириллица внутри латинских слов)
# ---------------------------------------------------------------------------

_CYR_TO_LAT = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X",
}
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


class Stats:
    def __init__(self) -> None:
        self.homoglyph_fixes: list[tuple[str, str]] = []


def fix_homoglyphs(text: str, stats: Stats | None = None) -> str:
    """
    "Masterсard" (кириллическая "с") -> "Mastercard".

    Меняем только слова, в которых латиница в большинстве и все кириллические
    буквы похожи на латинские. Обычные русские слова не затрагиваются.
    """

    def repl(match: re.Match) -> str:
        word = match.group(0)
        latin = len(_LATIN_RE.findall(word))
        cyr_letters = _CYRILLIC_RE.findall(word)
        if not latin or not cyr_letters:
            return word
        if latin < len(cyr_letters):
            return word
        if any(ch not in _CYR_TO_LAT for ch in cyr_letters):
            return word
        fixed = "".join(_CYR_TO_LAT.get(ch, ch) for ch in word)
        if stats is not None:
            stats.homoglyph_fixes.append((word, fixed))
        return fixed

    return _WORD_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# Загрузка сырых файлов
# ---------------------------------------------------------------------------

class Raw:
    """Находит файлы в папке сырых данных по имени (с расширением .json или без).

    Папки api_cards, api_branches и i18n читаются отдельно и в общий поиск
    по имени не попадают: иначе файл visa-gold.json из api_cards совпал бы
    по имени с уже имеющимся файлом visa-gold.
    """

    SEPARATE_DIRS = {"api_cards", "api_branches", "i18n", "manual_cards"}

    def __init__(self, root: Path) -> None:
        self.root = root
        self.missing: list[str] = []
        self.used: list[str] = []

    def load(self, name: str) -> dict | None:
        matches = [
            p for p in self.root.rglob("*")
            if p.is_file() and (p.name == name or p.stem == name)
            and not (set(p.relative_to(self.root).parts[:-1]) & self.SEPARATE_DIRS)
        ]
        if not matches:
            self.missing.append(name)
            return None
        if len(matches) > 1:
            raise RuntimeError(
                f"Найдено несколько файлов с именем '{name}': {matches}"
            )
        path = matches[0]
        self.used.append(str(path.relative_to(self.root)))
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)


def props(data: dict | None) -> dict:
    """Возвращает pageProps для файлов Next.js или сам словарь для прямых API-ответов."""
    if not isinstance(data, dict):
        return {}
    inner = data.get("pageProps")
    return inner if isinstance(inner, dict) else data


# ---------------------------------------------------------------------------
# Построение документов
# ---------------------------------------------------------------------------

class Builder:
    def __init__(self, raw: Raw, data_date: str) -> None:
        self.raw = raw
        self.data_date = data_date
        self.stats = Stats()
        self.gaps: list[str] = []
        self.skipped: list[str] = []

    # --- мелкие помощники -------------------------------------------------

    def text(self, value) -> str:
        return fix_homoglyphs(html_to_text(value), self.stats)

    def scalar(self, value):
        """Строка без мусора или None."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            cleaned = self.text(value)
            return cleaned or None
        return value

    def conditions(self, shorts) -> list[dict]:
        result = []
        for item in shorts or []:
            if not isinstance(item, dict):
                continue
            key = self.text(item.get("key"))
            value = self.text(item.get("value"))
            if key or value:
                result.append({"key": key, "value": value})
        return result

    # Имя файла -> платёжная система. Нужно, чтобы поймать ошибки сайта вроде
    # "Visa Gold ссылается на файл Mastercard_Gold".
    _BRANDS = {
        "visa": "Visa",
        "mastercard": "Mastercard",
        "elkart": "Элкарт",
        "elcart": "Элкарт",
        "элкарт": "Элкарт",
    }

    def brand_conflict(self, file_url: str, payment_system) -> str | None:
        """Название чужой платёжной системы в имени файла или None."""
        from urllib.parse import unquote

        name = unquote(file_url.rsplit("/", 1)[-1]).lower()
        found = {brand for key, brand in self._BRANDS.items() if key in name}
        if not found or not payment_system:
            return None
        if payment_system in found:
            return None
        if payment_system not in set(self._BRANDS.values()):
            return None  # например "Виртуальные карты": не сравниваем
        return ", ".join(sorted(found))

    def doc(
        self,
        section: str,
        slug: str,
        title: str,
        *,
        text: str = "",
        attributes: dict | None = None,
        conditions: list[dict] | None = None,
        documents: list[dict] | None = None,
        detail_level: str = "detail",
        kind: str = "info",
    ) -> dict:
        if section in ITEM_URL and slug:
            url = ITEM_URL[section].format(slug=slug)
        else:
            url = SECTION_URL.get(section)
        return {
            "id": f"{section}/{slug}",
            "section": section,
            "kind": kind,
            "title": title,
            "slug": slug,
            "detail_level": detail_level,
            "attributes": attributes or {},
            "conditions": conditions or [],
            "text": text,
            "documents": documents or [],
            "source_url": url,
            "data_date": self.data_date,
        }

    @staticmethod
    def join(*parts: str) -> str:
        seen, out = set(), []
        for part in parts:
            part = (part or "").strip()
            if part and part not in seen:
                seen.add(part)
                out.append(part)
        return "\n".join(out)

    def doc_links(self, items) -> list[dict]:
        links = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            url = item.get("file") or item.get("url")
            title = self.text(item.get("title"))
            if url:
                links.append({"title": title or "Документ", "url": url})
        return links

    # --- карты ------------------------------------------------------------

    _EMOJI_RE = re.compile(
        "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]+"
    )

    @staticmethod
    def dedupe_lines(text: str) -> str:
        """Убирает повторяющиеся строки (сайт часто дублирует абзац в кратком и полном описании)."""
        seen, out = set(), []
        for line in (text or "").split("\n"):
            key = line.strip().lstrip("•").strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(line)
        return "\n".join(out)

    @staticmethod
    def fee_value(value):
        """Приводит значение платы к сравнимому виду: число, 'free' или None."""
        if value is None:
            return None
        s = str(value).strip().lower()
        if not s:
            return None
        if s in ("бесплатно", "акысыз", "free", "0"):
            return "free"
        digits = re.sub(r"\D", "", s)
        return int(digits) if digits else s

    I18N_FEE_FIELDS = ("issuance", "annual_service", "account_opening")

    # Поля, которые уже признаны спорными (расходятся между языками сайта).
    # Обнуляются всегда, даже если файлов i18n нет: точные суммы в тексте.
    KNOWN_DISPUTED_FEES = {
        "elkart-beskontakt": ("issuance",),
    }

    def manual_cards(self) -> dict[str, dict]:
        """Карты, внесённые вручную из текста страницы: manual_cards/<slug>.json."""
        if hasattr(self, "_manual"):
            return self._manual
        self._manual = {}
        folder = self.raw.root / "manual_cards"
        for file in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            try:
                item = json.loads(file.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                self.gaps.append(f"cards: файл manual_cards/{file.name} не JSON, пропущен")
                continue
            if not (isinstance(item, dict) and item.get("slug") and item.get("overview")):
                self.gaps.append(f"cards: файл manual_cards/{file.name} без slug или overview, пропущен")
                continue
            self.raw.used.append(str(file.relative_to(self.raw.root)))
            self._manual[item["slug"]] = item
        return self._manual

    def i18n_cards(self, lang: str) -> dict[str, dict]:
        """Список карт на другом языке из i18n/<lang>/payment-cards.json (если файл есть)."""
        path = self.raw.root / "i18n" / lang / "payment-cards.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            self.gaps.append(f"cards: файл i18n/{lang}/payment-cards.json не JSON, пропущен")
            return {}
        self.raw.used.append(str(path.relative_to(self.raw.root)))
        results = (props(payload).get("data") or {}).get("results") or []
        return {c["slug"]: c for c in results if isinstance(c, dict) and c.get("slug")}

    CARD_DETAIL_FILES = [
        "elkart_beskontakt",
        "elkart_karta_pensionera",
        "elkart_socialnye_vyplaty",
        "elkart_business",
        "mastercardgold",
        "world-elite",
        "virtualnye_karty",
        "visa-gold",
        "visa-business",
        "visa_infinite",
    ]
    # visa_infinite.json содержит только список документов без карточки.
    CARD_DOCS_ONLY = {"visa_infinite": "visa-infinite"}

    def build_cards(self) -> list[dict]:
        listing = props(self.raw.load("payment-card_eldika")).get("data", {})
        cards = listing.get("results", []) if isinstance(listing, dict) else []
        if not cards:
            self.gaps.append("cards: не найден список карт (payment-card_eldika)")
            return []

        details_by_id: dict = {}
        details_by_slug: dict = {}
        extra_docs: dict[str, list[dict]] = {}

        for name in self.CARD_DETAIL_FILES:
            payload = props(self.raw.load(name))
            if not payload:
                continue

            card_docs = payload.get("cardDocs")
            if isinstance(card_docs, list):
                slug = self.CARD_DOCS_ONLY.get(name)
                if slug:
                    extra_docs.setdefault(slug, []).extend(self.doc_links(card_docs))
                continue

            detail = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            if isinstance(detail, dict) and detail.get("slug"):
                details_by_id[detail.get("id")] = detail
                details_by_slug[detail["slug"]] = detail
            else:
                self.gaps.append(
                    f"cards: файл '{name}' не содержит карточки карты (это оболочка "
                    f"страницы); скачайте /api/cards/<slug> и положите в api_cards/"
                )

        # Ответы /api/cards/<slug> (стабильный адрес, не зависит от buildId сайта).
        # Они главнее файлов Next.js: это тот же источник, что у самого сайта.
        api_dir = self.raw.root / "api_cards"
        for file in sorted(api_dir.glob("*.json")) if api_dir.is_dir() else []:
            try:
                detail = json.loads(file.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                self.gaps.append(f"cards: файл api_cards/{file.name} не JSON, пропущен")
                continue
            if not (isinstance(detail, dict) and detail.get("slug")):
                self.gaps.append(f"cards: файл api_cards/{file.name} без карточки, пропущен")
                continue
            self.raw.used.append(str(file.relative_to(self.raw.root)))
            details_by_id[detail.get("id")] = detail
            details_by_slug[detail["slug"]] = detail

        manual_cards = self.manual_cards()

        # Списки карт на других языках нужны только для сверки сумм.
        other_langs = {lang: self.i18n_cards(lang) for lang in ("ky", "en")}

        docs = []
        used_details = set()

        for card in cards:
            slug = card.get("slug")
            detail = details_by_slug.get(slug) or details_by_id.get(card.get("id"))
            if detail:
                used_details.add(detail["slug"])

            def pick(key: str):
                if detail and detail.get(key) not in (None, ""):
                    return detail.get(key)
                return card.get(key)

            category = (pick("category") or {}).get("name")
            payment_system = (pick("payment_system") or {}).get("name")
            # В сырых данных код сома "KGZ" (не ISO "KGS"), поэтому берём
            # название валюты, как его показывает сайт: СОМ, USD, EUR.
            currencies = [
                self.text(c.get("name") or c.get("code"))
                for c in (pick("currencies") or [])
                if isinstance(c, dict) and (c.get("name") or c.get("code"))
            ]
            category = self.scalar(category)
            payment_system = self.scalar(payment_system)

            attributes = {
                "category": category,
                "payment_system": payment_system,
                "audience": "business" if category == "Бизнес" else "individual",
                "currencies": currencies,
                "issuance": self.scalar(pick("issuance")),
                "annual_service": self.scalar(pick("annual_service")),
                "account_opening": self.scalar(pick("account_opening")),
                "card_expiration_date": self.scalar(pick("card_expiration_date")),
                "is_available": pick("is_available"),
                "is_creatable": pick("is_creatable"),
            }

            # Сверка сумм с версиями сайта на других языках. Редакторы ведут их
            # отдельно, и поле может значить разное (например, у ЭЛКАРТ Бесконтакт
            # в ru "выпуск 350 сом", а в ky/en "100 сом"; в описании 350 - это
            # перевыпуск, а 100 - годовое обслуживание). Если значения не совпали,
            # поле не используем: точные суммы остаются в тексте описания.
            for field in self.I18N_FEE_FIELDS:
                base = self.fee_value(attributes[field])
                if base is None:
                    continue
                for lang, others in other_langs.items():
                    other = others.get(slug)
                    if not other:
                        continue
                    alt = self.fee_value(other.get(field))
                    if alt is not None and alt != base:
                        self.gaps.append(
                            f"cards/{slug}: поле {field} расходится между языками "
                            f"(ru: {attributes[field]}; {lang}: {other.get(field)}); "
                            f"поле не используется, суммы смотрите в тексте"
                        )
                        attributes[field] = None
                        break

            for field in self.KNOWN_DISPUTED_FEES.get(slug, ()):
                if attributes.get(field) is not None:
                    self.gaps.append(
                        f"cards/{slug}: поле {field} известно как спорное "
                        f"(ru: {attributes[field]}); поле не используется, суммы смотрите в тексте"
                    )
                    attributes[field] = None

            parts =[self.text(pick("short_desc")), self.text(detail.get("desc")) if detail else ""]
            if detail:
                services = [
                    self.text(s.get("name"))
                    for s in detail.get("services") or []
                    if isinstance(s, dict) and s.get("name")
                ]
                if services:
                    parts.append("Услуги: " + ", ".join(services))
                for info in detail.get("owner_infos") or []:
                    if not isinstance(info, dict):
                        continue
                    body = self._EMOJI_RE.sub("", self.text(info.get("desc")))
                    body = "\n".join(ln.strip() for ln in body.split("\n") if ln.strip())
                    if body:
                        parts.append(body)
                advantages = []
                for adv in detail.get("advantages") or []:
                    if not isinstance(adv, dict):
                        continue
                    line = self.join(self.text(adv.get("title")), self.text(adv.get("short_desc")), self.text(adv.get("desc")))
                    if line:
                        advantages.append("• " + line.replace("\n", " "))
                if advantages:
                    parts.append("Преимущества:\n" + "\n".join(advantages))

            manual = manual_cards.get(slug)
            if manual:
                # Если есть ответ API, вручную добавляется только то, чего в нём нет.
                parts.append(self.text(manual.get("overview")))
                attributes.update(manual.get("attributes") or {})

            documents = self.doc_links(detail.get("docs") if detail else [])
            documents += extra_docs.get(slug, [])
            if manual:
                documents += self.doc_links(manual.get("documents"))
            seen_urls: set = set()
            documents = [d for d in documents if not (d["url"] in seen_urls or seen_urls.add(d["url"]))]
            tariff_file = detail.get("tariff_term_file") if detail else None
            if tariff_file:
                conflict = self.brand_conflict(tariff_file, payment_system)
                if conflict:
                    # Не смешиваем продукты: файл тарифов другой платёжной системы
                    # не прикрепляем к карте, а сообщаем о нём в отчёте.
                    self.gaps.append(
                        f"cards/{slug}: файл тарифов на странице карты относится к "
                        f"{conflict} ({tariff_file.rsplit('/', 1)[-1]}), а карта "
                        f"{payment_system}; ссылка не включена, проверьте на сайте"
                    )
                else:
                    documents.append({"title": "Тарифы и условия (PDF)", "url": tariff_file})

            doc = self.doc(
                "cards",
                slug,
                self.text(card.get("name")),
                text=self.dedupe_lines(self.join(*parts)),
                attributes=attributes,
                documents=documents,
                detail_level="detail" if (detail or manual) else "list",
            )
            if manual and manual.get("data_date"):
                doc["data_date"] = manual["data_date"]
            docs.append(doc)

            if manual:
                for note in manual.get("notes") or []:
                    self.gaps.append(f"cards/{slug}: {note}")

            if not detail and not manual:
                self.gaps.append(
                    f"cards/{slug}: нет детальной страницы, условия только из списка "
                    f"(поля null могут означать, что данные лежат в детальной странице)"
                )

        for slug in details_by_slug:
            if slug not in used_details:
                self.gaps.append(f"cards: детальный файл '{slug}' не нашёл пару в списке карт")
        return docs

    # --- продукты со списком shorts (кредиты, депозиты, исламские, переводы) ---

    def product_docs(self, section: str, items: list, extra_flags: bool = True) -> list[dict]:
        docs = []
        for item in items or []:
            if not isinstance(item, dict) or not item.get("slug"):
                continue
            attributes = {}
            if extra_flags:
                for flag in ("is_available", "is_creatable"):
                    if flag in item:
                        attributes[flag] = item.get(flag)
            docs.append(
                self.doc(
                    section,
                    item["slug"],
                    self.text(item.get("name")),
                    text=self.text(item.get("short_desc")),
                    attributes=attributes,
                    conditions=self.conditions(item.get("shorts")),
                    detail_level="list",
                )
            )
        return docs

    def build_credits(self) -> list[dict]:
        payload = props(self.raw.load("credits_eldika"))
        items = (payload.get("creditsList") or {}).get("results", [])
        docs = self.product_docs("credits", items)
        by_slug = {d["slug"]: d for d in docs}

        # Детальная страница кредитной карты.
        detail = props(self.raw.load("kreditnaya_karta")).get("data")
        if isinstance(detail, dict) and detail.get("slug"):
            target = by_slug.get(detail["slug"])
            if target is None:
                target = self.doc("credits", detail["slug"], self.text(detail.get("name")), detail_level="detail")
                docs.append(target)
                by_slug[detail["slug"]] = target
            advantages = []
            for adv in detail.get("advantages") or []:
                if isinstance(adv, dict):
                    line = self.join(self.text(adv.get("title")), self.text(adv.get("desc")))
                    if line:
                        advantages.append("• " + line.replace("\n", " "))
            target["text"] = self.join(
                target["text"],
                self.text(detail.get("main_desc")),
                self.text(detail.get("second_desc")),
                ("Преимущества:\n" + "\n".join(advantages)) if advantages else "",
            )
            if not target["conditions"]:
                target["conditions"] = self.conditions(detail.get("shorts"))
            target["detail_level"] = "detail"
        else:
            self.gaps.append("credits: нет детальной страницы кредитной карты")

        for d in docs:
            if d["detail_level"] == "list":
                self.gaps.append(
                    f"credits/{d['slug']}: только краткие условия (shorts), детальной страницы нет"
                )
        return docs

    def build_deposits(self) -> list[dict]:
        payload = props(self.raw.load("depozits_eldika"))
        items = (payload.get("data") or {}).get("deposits", [])
        docs = self.product_docs("deposits", items)
        for d in docs:
            self.gaps.append(f"deposits/{d['slug']}: только краткие условия, детальной страницы нет")
        return docs

    def build_islamic(self) -> list[dict]:
        payload = props(self.raw.load("islamic_window_eldika"))
        items = (payload.get("products") or {}).get("results", [])
        docs = self.product_docs("islamic", items, extra_flags=False)
        if payload.get("branches"):
            self.skipped.append("islamic_window_eldika: отделения вынесены в locations.json")
        return docs

    def build_transfers(self) -> list[dict]:
        payload = props(self.raw.load("transfers_eldika"))
        items = (payload.get("transfers") or {}).get("results", [])
        docs = self.product_docs("transfers", items, extra_flags=False)
        return docs

    # --- страницы без списка продуктов -------------------------------------

    def build_overdraft(self) -> list[dict]:
        data = props(self.raw.load("overdraft")).get("data")
        if not isinstance(data, dict):
            self.gaps.append("overdraft: файл не найден")
            return []

        conditions = [
            {"key": self.text(p.get("title")), "value": self.text(p.get("desc"))}
            for p in data.get("properties") or []
            if isinstance(p, dict)
        ]
        steps = [self.text(s.get("desc")) for s in data.get("steps") or [] if isinstance(s, dict)]
        faq = []
        for sec in data.get("sections") or []:
            if isinstance(sec, dict):
                block = self.join(self.text(sec.get("title")), self.text(sec.get("desc")))
                if block:
                    faq.append(block)

        text = self.join(
            self.text(data.get("about")),
            ("Что нужно для оформления: " + "; ".join(s for s in steps if s)) if steps else "",
            "\n\n".join(faq),
        )
        return [
            self.doc(
                "overdraft", "overdraft", "Овердрафт",
                text=text, conditions=conditions,
                documents=self.doc_links([data.get("personal_data_processing") or {}]),
            )
        ]

    def build_salary_project(self) -> list[dict]:
        payload = props(self.raw.load("salary-project"))
        data = payload.get("data")
        if not isinstance(data, dict):
            self.gaps.append("salary_project: файл не найден")
            return []

        blocks = []
        for sec in data.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            title = self.text(sec.get("title"))
            items = [
                "• " + self.text(i.get("title"))
                for i in sec.get("icons") or []
                if isinstance(i, dict) and i.get("title")
            ]
            blocks.append(self.join(title, "\n".join(items), self.text(sec.get("desc"))))

        if payload.get("points"):
            self.skipped.append(
                f"salary-project: {len(payload['points'])} точек вынесены в locations.json"
            )
        return [
            self.doc(
                "salary_project", "salary-project", "Зарплатный проект",
                text=self.join(self.text(data.get("about")), *blocks),
            )
        ]

    def build_accounts(self) -> list[dict]:
        data = props(self.raw.load("otkrytie-bankovskogo-scheta_eldika")).get("data")
        if not isinstance(data, dict):
            self.gaps.append("accounts: файл не найден")
            return []
        sections = [
            self.join(self.text(s.get("title")), self.text(s.get("desc")))
            for s in data.get("sections") or []
            if isinstance(s, dict)
        ]
        return [
            self.doc(
                "accounts",
                data.get("slug") or "otkrytie-bankovskogo-scheta",
                self.text(data.get("main_title")) or "Открытие банковского счёта",
                text=self.join(self.text(data.get("main_desc")), self.text(data.get("caption")), *sections),
            )
        ]

    def build_mobile_banking(self) -> tuple[list[dict], list[dict]]:
        data = props(self.raw.load("mobile-banking_eldika")).get("data")
        if not isinstance(data, dict):
            self.gaps.append("mobile_banking: файл не найден")
            return [], []

        regular, legal = [], []
        for sec in data.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            sec_title = self.text(sec.get("title"))
            for block in sec.get("blocks") or []:
                if not isinstance(block, dict):
                    continue
                block_title = self.text(block.get("title"))
                is_legal = any(
                    k in (block_title + " " + sec_title).lower() for k in LEGAL_KEYWORDS
                )
                # У юридических блоков заголовок часто равен первой фразе текста,
                # поэтому берём короткое название раздела.
                title = (sec_title if is_legal else block_title) or sec_title

                # infos - список возможностей приложения ("Оплачивайте ЖКХ", ...).
                infos = [
                    "• " + self.text(i.get("title"))
                    for i in block.get("infos") or []
                    if isinstance(i, dict) and self.text(i.get("title"))
                ]
                body = self.join(
                    self.text(block.get("desc")),
                    self.text(block.get("caption")),
                    "\n".join(infos),
                )
                documents = self.doc_links(block.get("docs"))
                if not body and not documents:
                    continue
                slug = f"{sec.get('id')}-{block.get('id')}"
                doc = self.doc(
                    "legal" if is_legal else "mobile_banking",
                    slug,
                    title,
                    text=body,
                    documents=documents,
                    kind="legal" if is_legal else "instruction",
                )
                (legal if is_legal else regular).append(doc)

        links = {
            "google_play": data.get("google_play_link"),
            "app_store": data.get("app_store_link"),
        }
        if any(links.values()):
            regular.append(
                self.doc(
                    "mobile_banking", "app-links", "Ссылки на мобильное приложение",
                    text="Скачать приложение ELDIK можно в Google Play и App Store.",
                    attributes=links,
                )
            )
        return regular, legal

    def build_tariffs(self) -> list[dict]:
        payload = props(self.raw.load("tarifs_eldika"))
        data = payload.get("data") or {}
        items = data.get("results", [])
        docs = []
        for item in items:
            if not isinstance(item, dict) or not item.get("file"):
                continue
            docs.append(
                self.doc(
                    "tariffs", str(item.get("id")), self.text(item.get("title")),
                    attributes={"ext": item.get("ext"), "text_extracted": False},
                    documents=[{"title": self.text(item.get("title")), "url": item["file"]}],
                    detail_level="list",
                    kind="document_link",
                )
            )
        total = data.get("count")
        if isinstance(total, int) and total > len(docs):
            self.gaps.append(
                f"tariffs: собрано {len(docs)} из {total} документов (нужна вторая страница списка)"
            )
        if docs:
            self.gaps.append(
                "tariffs: хранятся только названия и ссылки на PDF, текст тарифов не извлечён"
            )
        return docs

    # --- точки обслуживания: банкоматы, филиалы, кассы -----------------------

    _KIND_BY_TYPE = {
        "филиал": "branch",
        "сберегательная касса": "savings_cash",
        "выездная касса": "mobile_cash",
        "банкомат": "atm",
        "atm": "atm",
        "branch": "branch",
    }

    def _location(self, item: dict, source: str, region_name: str | None = None) -> dict | None:
        if not isinstance(item, dict):
            return None
        lat, lng = item.get("lat"), item.get("lng")
        try:
            lat, lng = round(float(lat), 6), round(float(lng), 6)
        except (TypeError, ValueError):
            lat = lng = None

        raw_type = (item.get("type") or item.get("branch_type_display") or item.get("branch_type") or "")
        kind = "other"
        for key, value in self._KIND_BY_TYPE.items():
            if key in str(raw_type).lower():
                kind = value
                break

        region = item.get("region") if isinstance(item.get("region"), dict) else {}
        city = item.get("city") if isinstance(item.get("city"), dict) else {}
        name = self.text(item.get("name"))
        address = self.text(item.get("address"))
        if not name and not address:
            return None

        # Имена и телефоны конкретных сотрудников (specialist_*) не берём.
        phones = [
            p.get("phone") for p in item.get("phones") or []
            if isinstance(p, dict) and p.get("phone")
        ]
        # Поля status/is_open/day_n_night не сохраняем: это снимок на момент
        # скачивания (например "Открыто до 22:00"), а не график работы.
        return {
            "id": item.get("slug") or f"{source}-{item.get('id')}",
            "kind": kind,
            "name": name,
            "address": address,
            "region": self.text(region.get("name")) or region_name,
            "city": self.text(city.get("name")) or None,
            "phones": phones,
            "lat": lat,
            "lng": lng,
        }

    def build_locations(self) -> list[dict]:
        found: dict[str, dict] = {}

        def add(loc: dict | None) -> None:
            if loc and loc["id"] not in found:
                found[loc["id"]] = loc

        pin = props(self.raw.load("change-pin-code"))
        for item in pin.get("bankomats") or []:
            add(self._location(item, "atm"))
        for item in pin.get("branches") or []:
            add(self._location(item, "branch"))

        # Ответы /api/branches?region=N, по одному файлу на область (массив точек).
        api_dir = self.raw.root / "api_branches"
        api_files = sorted(api_dir.glob("*")) if api_dir.is_dir() else []
        api_regions: set[str] = set()
        for file in api_files:
            if not file.is_file():
                continue
            try:
                items = json.loads(file.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                self.gaps.append(f"locations: файл {file.name} не JSON, пропущен")
                continue
            if isinstance(items, dict):
                items = items.get("results") or items.get("branches") or []
            for item in items:
                loc = self._location(item, "api")
                add(loc)
                if loc and loc["region"]:
                    api_regions.add(loc["region"])
        salary = props(self.raw.load("salary-project"))
        for item in salary.get("points") or []:
            add(self._location(item, "point"))

        islamic = props(self.raw.load("islamic_window_eldika"))
        regions = (islamic.get("branches") or {}).get("regions") or []
        for reg in regions:
            if not isinstance(reg, dict):
                continue
            for item in reg.get("branches") or []:
                add(self._location(item, "islamic", self.text(reg.get("region_name"))))

        if api_files:
            all_regions = {
                "Баткенская область", "Жалал-Абадская область", "Иссык-кульская область",
                "Нарынская область", "Ошская область", "Таласская область",
                "Чуйская область", "г. Бишкек",
            }
            absent = sorted(all_regions - api_regions)
            if absent:
                self.gaps.append(
                    "locations: нет файла /api/branches для: " + ", ".join(absent)
                    + " (эти области взяты из других страниц сайта и могут быть неполными)"
                )

        locations = sorted(found.values(), key=lambda x: (x["kind"], x["region"] or "", x["name"]))
        atm_regions = {l["region"] for l in locations if l["kind"] == "atm"}
        if locations:
            self.gaps.append(
                "locations: режим работы не сохраняется (в файлах только снимок статуса); "
                f"банкоматы есть только в регионах: {', '.join(sorted(r for r in atm_regions if r)) or 'нет'}"
            )
        else:
            self.gaps.append("locations: точки обслуживания не найдены")
        return locations

    def build_card_privileges(self) -> list[dict]:
        """Подробности привилегий премиальных карт (всплывающие окна на странице карты)."""
        docs = []
        card_names = {}
        try:
            card_names = {c.get("slug"): c.get("name")
                          for c in (props(self.raw.load("payment-card_eldika")).get("data", {}) or {}).get("results", [])}
        except (AttributeError, TypeError):
            pass
        for slug, manual in self.manual_cards().items():
            card_name = self.text(card_names.get(slug) or slug)
            for priv in manual.get("privileges") or []:
                if not (priv.get("slug") and priv.get("title") and priv.get("text")):
                    continue
                attributes = {"card": card_name, "card_slug": slug, "audience": "individual"}
                as_of = manual.get("data_date") or self.data_date
                if priv.get("valid_until"):
                    attributes["valid_until"] = priv["valid_until"]
                    if priv["valid_until"] < as_of:
                        self.gaps.append(
                            f"card_privileges/{slug}-{priv['slug']}: срок 'до {priv['valid_until']}' "
                            f"уже прошёл на дату данных ({as_of}); действует ли программа, неизвестно"
                        )
                if priv.get("offers"):
                    attributes["offers"] = priv["offers"]
                    past = [o["partner"] for o in priv["offers"] if o.get("valid_until", "9999") < as_of]
                    if past:
                        self.gaps.append(
                            f"card_privileges/{slug}-{priv['slug']}: у предложений срок уже прошёл "
                            f"на дату данных ({as_of}): {', '.join(past)}"
                        )
                doc = self.doc(
                    "card_privileges",
                    f"{slug}-{priv['slug']}",
                    f"{card_name}: {self.text(priv['title'])}",
                    text=self.text(priv["text"]),
                    attributes=attributes,
                )
                doc["source_url"] = manual.get("source_url") or SECTION_URL["card_privileges"]
                if manual.get("data_date"):
                    doc["data_date"] = manual["data_date"]
                docs.append(doc)
        return docs

    def build_instructions(self) -> list[dict]:
        """Инструкция по смене PIN: тексты лежат в строках интерфейса страницы."""
        payload = props(self.raw.load("change-pin-code"))
        store = ((payload.get("_nextI18Next") or {}).get("initialI18nStore") or {})
        ru = (store.get("ru") or {}).get("common", {}).get("cards", {})
        if not ru.get("select_pin_change_atm"):
            self.gaps.append("инструкция по смене PIN-кода: нет в собранных данных")
            return []

        def steps(*keys: str) -> str:
            lines = [ru[k].strip() for k in keys if ru.get(k)]
            return "\n".join(f"{i}. {line}" for i, line in enumerate(lines, 1))

        text = self.join(
            "Сменить ПИН-код карты можно тремя способами.",
            "1) В приложении:\n" + steps(
                "download_eldik_app", "select_required_card", "select_pin_change",
                "enter_new_pin", "confirm_new_pin", "pin_changed",
            ),
            "2) В банкомате:\n" + steps(
                "insert_card_atm", "select_language", "enter_card_pin",
                "select_pin_change_atm", "enter_old_pin", "enter_new_pin",
                "confirm_new_pin", "pin_changed",
            ),
            "3) В отделении банка:\n" + steps("select_bank_branch", "insert_card_pos")
            + "\n" + (ru.get("bank_branch_description") or ""),
        )
        self.gaps.append(
            "инструкция по смене PIN-кода собрана из строк интерфейса страницы; "
            "порядок шагов сверить со страницей сайта"
        )
        return [
            self.doc(
                "instructions", "change-pin-code", "Как сменить ПИН-код карты",
                text=text,
                attributes={"assembled_from_ui_strings": True},
                kind="instruction",
            )
        ]

    def skip_known(self) -> None:
        payload = props(self.raw.load("change-pin-code"))
        if payload:
            self.skipped.append(
                "change-pin-code: банкоматы и отделения вынесены в locations.json, "
                "инструкция по PIN собрана в раздел instructions"
            )


# ---------------------------------------------------------------------------
# Запись и отчёт
# ---------------------------------------------------------------------------

TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def validate(sections: dict[str, list[dict]]) -> list[str]:
    problems = []
    for section, docs in sections.items():
        seen = set()
        for doc in docs:
            blob = json.dumps(doc, ensure_ascii=False)
            if "_nextI18Next" in blob:
                problems.append(f"{doc['id']}: остался блок _nextI18Next")
            if TAG_RE.search(doc["text"]):
                problems.append(f"{doc['id']}: в тексте остались HTML-теги")
            if not doc["title"]:
                problems.append(f"{doc['id']}: пустой заголовок")
            if doc["id"] in seen:
                problems.append(f"{doc['id']}: дублирующийся id")
            seen.add(doc["id"])
    return problems


def write_json(path: Path, payload: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")
    return len(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сборка базы знаний из сырых JSON сайта.")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="папка с сырыми файлами")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="куда писать результат")
    parser.add_argument("--data-date", default=date.today().isoformat(),
                        help="дата скачивания данных (ГГГГ-ММ-ДД)")
    args = parser.parse_args(argv)

    if not args.raw.is_dir():
        print(f"Папка с сырыми данными не найдена: {args.raw}", file=sys.stderr)
        return 1

    raw = Raw(args.raw)
    builder = Builder(raw, args.data_date)
    builder.skip_known()

    mobile_docs, legal_docs = builder.build_mobile_banking()
    sections: dict[str, list[dict]] = {
        "cards": builder.build_cards(),
        "credits": builder.build_credits(),
        "deposits": builder.build_deposits(),
        "overdraft": builder.build_overdraft(),
        "transfers": builder.build_transfers(),
        "accounts": builder.build_accounts(),
        "islamic": builder.build_islamic(),
        "salary_project": builder.build_salary_project(),
        "mobile_banking": mobile_docs,
        "instructions": builder.build_instructions(),
        "card_privileges": builder.build_card_privileges(),
        "tariffs": builder.build_tariffs(),
        "legal": legal_docs,
    }

    problems = validate(sections)
    locations = builder.build_locations()

    manifest_sections = {}
    total_bytes = 0
    for name, docs in sections.items():
        payload = {"section": name, "data_date": args.data_date, "documents": docs}
        size = write_json(args.out / f"{name}.json", payload)
        total_bytes += size
        manifest_sections[name] = {
            "documents": len(docs),
            "text_chars": sum(len(d["text"]) for d in docs),
            "file_bytes": size,
        }

    # Точки обслуживания - отдельный набор (не "документы"), см. knowledge.find_locations.
    loc_size = write_json(
        args.out / "locations.json",
        {"section": "locations", "data_date": args.data_date, "items": locations},
    )
    total_bytes += loc_size
    manifest_sections["locations"] = {
        "documents": len(locations),
        "text_chars": 0,
        "file_bytes": loc_size,
    }

    manifest = {
        "data_date": args.data_date,
        "sections": manifest_sections,
        "gaps": builder.gaps,
        "skipped": builder.skipped,
        "missing_raw_files": raw.missing,
        "homoglyph_fixes": sorted({f"{a} -> {b}" for a, b in builder.stats.homoglyph_fixes}),
        "validation_problems": problems,
    }
    write_json(args.out / "_manifest.json", manifest)

    # --- отчёт в консоль ---
    print(f"Источник: {args.raw}")
    print(f"Результат: {args.out}\n")
    print(f"{'Раздел':<16}{'Документов':>11}{'Символов текста':>18}{'Файл, КБ':>10}")
    for name, info in manifest_sections.items():
        print(f"{name:<16}{info['documents']:>11}{info['text_chars']:>18}{info['file_bytes'] / 1024:>10.1f}")
    print(f"\nИтого: {total_bytes / 1024:.0f} КБ")

    if manifest["homoglyph_fixes"]:
        print("\nИсправлены буквы-двойники:", ", ".join(manifest["homoglyph_fixes"]))
    if raw.missing:
        print("\nНЕ НАЙДЕНЫ исходные файлы:", ", ".join(raw.missing))
    if builder.skipped:
        print("\nНамеренно не включено:")
        for item in builder.skipped:
            print("  -", item)
    if builder.gaps:
        print(f"\nПробелы в данных ({len(builder.gaps)}):")
        for item in builder.gaps:
            print("  -", item)
    if problems:
        print("\nПРОБЛЕМЫ ВАЛИДАЦИИ:")
        for item in problems:
            print("  !", item)
        return 2

    print("\nВалидация пройдена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
