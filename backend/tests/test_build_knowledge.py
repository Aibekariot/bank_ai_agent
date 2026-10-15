"""
Тесты скрипта scripts/build_knowledge.py.

Запуск (из папки backend):
    python tests/test_build_knowledge.py

Не требуют ни базы данных, ни интернета, ни ключей API.
Интеграционная часть работает на ваших реальных файлах из jisonki_eldika.
"""

import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))

import build_knowledge as bk  # noqa: E402

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


# --- HTML -> текст -----------------------------------------------------------

check("теги и entities убираются",
      bk.html_to_text("<p>Карта &laquo;Элдик&raquo;&nbsp;Gold</p>") == "Карта «Элдик» Gold")

check("списки становятся строками с маркером",
      bk.html_to_text("<ul><li>Один</li><li>Два</li></ul>") == "• Один\n• Два")

check("ячейки таблицы разделяются",
      "Срок | 12 месяцев" in bk.html_to_text("<table><tr><td>Срок</td><td>12 месяцев</td></tr></table>"))

check("None и пустая строка дают пустой текст",
      bk.html_to_text(None) == "" and bk.html_to_text("  ") == "")

check("script/style не попадают в текст",
      bk.html_to_text("<style>p{}</style><p>Текст</p><script>x()</script>") == "Текст")

# --- буквы-двойники ----------------------------------------------------------

stats = bk.Stats()
check("кириллическая 'с' внутри Masterсard исправляется",
      bk.fix_homoglyphs("Masterсard Gold", stats) == "Mastercard Gold")
check("обычные русские слова не затрагиваются",
      bk.fix_homoglyphs("Оплата картой за границей") == "Оплата картой за границей")
check("слово ЭЛКАРТ (чисто кириллица) не меняется",
      bk.fix_homoglyphs("ЭЛКАРТ Бизнес") == "ЭЛКАРТ Бизнес")

# --- сверка сумм между языками и чистка текста -------------------------------

check("fee_value: 'Бесплатно', 'Акысыз', 'Free' равны",
      bk.Builder.fee_value("Бесплатно") == bk.Builder.fee_value("Акысыз") == bk.Builder.fee_value("Free"))
check("fee_value: '10 000 сом' и '10 000 KGS' равны",
      bk.Builder.fee_value("10 000 сом") == bk.Builder.fee_value("10 000 KGS") == 10000)
check("fee_value: 350 и 100 различаются",
      bk.Builder.fee_value("350 сом") != bk.Builder.fee_value("100 сом"))
check("fee_value: пусто даёт None", bk.Builder.fee_value(None) is None and bk.Builder.fee_value("") is None)
check("dedupe_lines убирает повтор строки, в том числе с маркером списка",
      bk.Builder.dedupe_lines("A\n• Б\nБ\nA\nВ") == "A\n• Б\nВ")

# --- интеграция на реальных данных -------------------------------------------

raw_dir = bk.DEFAULT_RAW
if raw_dir.is_dir():
    with tempfile.TemporaryDirectory() as tmp:
        code = bk.main(["--raw", str(raw_dir), "--out", tmp, "--data-date", "2026-01-01"])
        out = Path(tmp)
        check("скрипт завершился без проблем валидации", code == 0)

        cards = {d["slug"]: d for d in json.loads((out / "cards.json").read_text(encoding="utf-8"))["documents"]}
        gold = cards.get("visa-gold")
        check("Visa Gold найдена", gold is not None)
        if gold:
            check("условия обслуживания Visa Gold попали в текст из детальной страницы",
                  "500 сом" in gold["text"] and "Годовое обслуживание" in gold["text"])
            check("пустое поле annual_service остаётся None (не 'бесплатно')",
                  gold["attributes"]["annual_service"] is None)
            check("у карты есть источник и дата",
                  gold["source_url"] and gold["data_date"] == "2026-01-01")

        check("ЭЛКАРТ Бесконтакт: спорное поле issuance не используется, суммы остались в тексте",
              cards["elkart-beskontakt"]["attributes"]["issuance"] is None
              and "Перевыпуск карты по истечении срока действия – 350 сом" in cards["elkart-beskontakt"]["text"]
              and "Годовое обслуживание – 100 сом" in cards["elkart-beskontakt"]["text"])
        virt = cards["virtualnye-karty"]["text"]
        check("виртуальная карта: срок действия 3 года из owner_infos попал в текст",
              "Срок действия – 3 года" in virt)
        check("в тексте нет эмодзи и повторов шагов оформления",
              "✨" not in virt and virt.count("Нажмите «Заказать виртуальную карту»") == 1)
        soc = cards["elkart-socialnye-vyplaty"]["text"]
        check("социальная карта: абзац описания не дублируется",
              soc.count("это социальная карта позволяет") == 1)

        priv = {d["slug"]: d for d in json.loads((out / "card_privileges.json").read_text(encoding="utf-8"))["documents"]}
        we_priv = [k for k in priv if k.startswith("mastercard-world-elite-")]
        vi_priv = [k for k in priv if k.startswith("visa-infinite-")]
        check("World Elite: 6 привилегий отдельными записями", len(we_priv) == 6)
        check("Visa Infinite: 11 привилегий отдельными записями", len(vi_priv) == 11)
        vi = cards["visa-infinite"]
        check("Visa Infinite: обслуживание 10 000 сом, карточка подробная",
              vi["attributes"]["annual_service"] == "10 000 сом" and vi["detail_level"] == "detail")
        urls = [d["url"] for d in vi["documents"]]
        check("Visa Infinite: документы без повторов, тарифы добавлены",
              len(urls) == len(set(urls)) and any("tariffs" in u for u in urls))
        check("Visa Infinite: сроки 'до 30.09.2026' записаны в пробелы как истёкшие",
              any("fast-track" in g and "прошёл" in g for g in
                  json.loads((out / "_manifest.json").read_text(encoding="utf-8"))["gaps"]))
        check("Visa Infinite: у скидок хранятся даты окончания по партнёрам",
              len(priv["visa-infinite-visa-offers"]["attributes"]["offers"]) == 10)
        check("World Elite: карточка теперь подробная, с PDF тарифов и ручной датой",
              cards["mastercard-world-elite"]["detail_level"] == "detail"
              and any(x["url"].endswith(".pdf") for x in cards["mastercard-world-elite"]["documents"])
              and cards["mastercard-world-elite"]["data_date"] == "2026-10-15")
        manifest = json.loads((out / "_manifest.json").read_text(encoding="utf-8"))
        check("расхождение по страхованию записано в пробелы",
              any("страхование" in g and "1 500 000" in g for g in manifest["gaps"]))

        check("бизнес-карты помечены audience=business",
              any(d["attributes"]["audience"] == "business" for d in cards.values()))

        all_text = "".join(p.read_text(encoding="utf-8") for p in out.glob("*.json"))
        check("в результате нет блока _nextI18Next", "_nextI18Next" not in all_text)

        legal = json.loads((out / "legal.json").read_text(encoding="utf-8"))["documents"]
        mobile = json.loads((out / "mobile_banking.json").read_text(encoding="utf-8"))["documents"]
        check("юридические тексты отделены от инструкций",
              len(legal) >= 1 and all(len(d["text"]) < 5000 for d in mobile))

        total = sum(p.stat().st_size for p in out.glob("*.json"))
        check("вся база знаний меньше 1 МБ", total < 1_000_000)
else:
    print("SKIP интеграционные проверки: папка jisonki_eldika не найдена")


# --- api_cards и i18n на синтетических данных --------------------------------

with tempfile.TemporaryDirectory() as tmp:
    raw = Path(tmp) / "raw"
    (raw / "api_cards").mkdir(parents=True)
    (raw / "i18n" / "ky").mkdir(parents=True)
    listing = {"pageProps": {"data": {"results": [{
        "id": 1, "slug": "test-card", "name": "Тест", "short_desc": "<p>Кратко</p>",
        "issuance": "100 сом", "annual_service": "Бесплатно", "account_opening": None,
        "category": {"name": "Дебетовые карты"}, "payment_system": {"name": "Visa"},
        "currencies": [{"name": "СОМ"}], "card_expiration_date": "5 лет",
        "is_available": True, "is_creatable": True}]}}}
    (raw / "payment-card_eldika").write_text(json.dumps(listing, ensure_ascii=False), encoding="utf-8")
    detail = {"id": 1, "slug": "test-card", "name": "Тест", "desc": "<p>Подробно</p>",
              "issuance": "100 сом", "annual_service": "Бесплатно", "category": {"name": "Дебетовые карты"},
              "payment_system": {"name": "Visa"}, "currencies": [], "owner_infos": [{"desc": "<p>✨ Срок – 3 года</p>"}]}
    (raw / "api_cards" / "test-card.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    ky_listing = json.loads(json.dumps(listing))
    ky_listing["pageProps"]["data"]["results"][0]["issuance"] = "350 сом"
    ky_listing["pageProps"]["data"]["results"][0]["annual_service"] = "Акысыз"
    (raw / "i18n" / "ky" / "payment-cards.json").write_text(json.dumps(ky_listing, ensure_ascii=False), encoding="utf-8")

    builder = bk.Builder(bk.Raw(raw), "2026-01-01")
    docs = builder.build_cards()
    check("карта берётся из api_cards (детальная версия)", docs and docs[0]["detail_level"] == "detail")
    check("owner_infos из api_cards попали в текст без эмодзи",
          docs and "Срок – 3 года" in docs[0]["text"] and "✨" not in docs[0]["text"])
    check("расходящееся поле обнулено, совпадающее ('Бесплатно' = 'Акысыз') сохранено",
          docs and docs[0]["attributes"]["issuance"] is None
          and docs[0]["attributes"]["annual_service"] == "Бесплатно")
    check("расхождение записано в пробелы",
          any("issuance" in g and "расходится" in g for g in builder.gaps))

print("\nИТОГ:", "ВСЕ ТЕСТЫ ПРОШЛИ" if ok else "ЕСТЬ ПАДЕНИЯ")
sys.exit(0 if ok else 1)
