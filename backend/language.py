"""
language.py - определение языка сообщения пользователя (ru / ky / en).

Зачем: бесплатная модель часто игнорирует правило "отвечай на языке
пользователя" из системного промпта. Поэтому язык определяется кодом,
а в запрос к модели добавляется короткая подсказка (см. agent.py), и
отказы тоже выдаются на нужном языке.

Определение простое и быстрое (без внешних библиотек):
  * кыргызский: есть буквы ң, ө, ү или характерные слова;
  * английский: нет кириллицы и есть английские служебные слова;
  * иначе русский.

ВАЖНО: список кыргызских слов составлен по общим знаниям и требует
проверки носителем языка. Дополняйте KY_WORDS по реальным вопросам.
"""

from __future__ import annotations

import re

# Буквы, которых нет в русском алфавите.
_KY_LETTERS = set("ңөүҢӨҮ")

# Слова, которые в русском языке не встречаются. Только однозначные.
KY_WORDS = {
    "кандай", "канча", "кантип", "качан", "кайда", "эмне", "эмнеге",
    "керек", "болот", "болобу", "барбы", "жокпу", "келет", "алгым",
    "алам", "алсам", "берет", "берсеңиз", "бериңиз", "бере", "аласыз",
    "үчүн", "менен", "жана", "жөнүндө", "тууралуу", "сураныч",
    "рахмат", "салам", "саламатсызбы", "кредиттер", "кредиттин",
    "шарттар", "шарты", "шарттары", "пайыз", "пайызы", "төлөм",
    "акча", "эсеп", "насыя", "салым", "аудар", "которуу", "тиркеме",
    "мобилдик", "карталар", "картасы", "картам", "канчалык",
    "айлык", "бекер", "акысыз", "жеңилдик",
    "мага", "сизде", "сиздин", "менин", "биздин", "кимге",
}
# Слова, совпадающие с русскими ("бар", "бир", "жок", "ай"), сюда не включены.

_EN_WORDS = {
    "the", "what", "how", "is", "are", "do", "does", "can", "could",
    "i", "you", "my", "me", "about", "please", "hello", "hi", "thanks",
    "thank", "card", "loan", "bank", "account", "want", "need", "tell",
    "which", "where", "when", "why", "much", "show", "give", "of", "to",
}

_WORD_RE = re.compile(r"[a-zа-яёңөү]+", re.IGNORECASE)
_CYRILLIC_RE = re.compile(r"[а-яёңөү]", re.IGNORECASE)


def detect_language(text: str) -> str:
    """Возвращает 'ky', 'en' или 'ru' (по умолчанию)."""
    text = (text or "").strip()
    if not text:
        return "ru"

    if any(ch in _KY_LETTERS for ch in text):
        return "ky"

    words = [w.lower() for w in _WORD_RE.findall(text)]

    if any(w in KY_WORDS for w in words):
        return "ky"

    if not _CYRILLIC_RE.search(text):
        english = sum(1 for w in words if w in _EN_WORDS)
        if english >= 2 or (english >= 1 and len(words) <= 3):
            return "en"

    return "ru"


_HINTS = {
    "ky": (
        "[Системная подсказка: пользователь пишет по-кыргызски. "
        "Ответь полностью на кыргызском языке. Названия продуктов и "
        "цифры оставь как в данных.]"
    ),
    "en": (
        "[System hint: the user writes in English. "
        "Reply fully in English. Keep product names and figures as in the data.]"
    ),
}


def language_hint(text: str) -> str | None:
    """Подсказка модели о языке ответа. Для русского не нужна (None)."""
    return _HINTS.get(detect_language(text))


REFUSALS = {
    "ru": (
        "Я консультант по продуктам и услугам Элдик Банка. "
        "Могу помочь с картами, кредитами, вкладами, курсами валют, "
        "тарифами, переводами, счетами и другими банковскими вопросами."
    ),
    "ky": (
        "Мен Элдик Банктын продуктулары жана кызматтары боюнча "
        "консультантмын. Карталар, кредиттер, депозиттер, валюта курстары, "
        "тарифтер, акча которуулар, эсептер жана башка банк суроолору "
        "боюнча жардам бере алам."
    ),
    "en": (
        "I am a consultant for Eldik Bank products and services. "
        "I can help with cards, loans, deposits, exchange rates, tariffs, "
        "transfers, accounts and other banking questions."
    ),
}


def refusal_for(text: str) -> str:
    return REFUSALS[detect_language(text)]
