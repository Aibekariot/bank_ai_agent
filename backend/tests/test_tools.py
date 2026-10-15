"""
Тесты инструментов агента (tools.py) на реальной базе знаний.

Запуск (из папки backend):
    python tests/test_tools.py

Как это работает: тест собирает базу знаний из ваших файлов jisonki_eldika
во временную папку, подключает её к knowledge.py и вызывает инструменты так,
как это делает агент. Нужны только Python и ваши файлы: без базы данных,
интернета и ключей API.
"""

import json
import sys
import tempfile
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

# httpx нужен только живым запросам курсов; для тестов хватит заглушки.
try:
    import httpx  # noqa: F401
except ImportError:
    sys.modules["httpx"] = types.ModuleType("httpx")

import build_knowledge as bk  # noqa: E402
import knowledge  # noqa: E402
import tools  # noqa: E402
import eldik_client  # noqa: E402

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


def names(result):
    return [i.get("name") or i.get("title") for i in result.get("items", [])]


if not bk.DEFAULT_RAW.is_dir():
    print("Папка jisonki_eldika не найдена, тесты невозможны:", bk.DEFAULT_RAW)
    sys.exit(1)

tmp = tempfile.TemporaryDirectory()
code = bk.main(["--raw", str(bk.DEFAULT_RAW), "--out", tmp.name, "--data-date", "2026-01-01"])
check("база знаний собралась без проблем валидации", code == 0)
knowledge.reload(tmp.name)


# Любой запрос к сайту во время тестов - ошибка: инструменты продуктов не должны
# ходить в интернет.
def _no_network(*a, **k):
    raise AssertionError("инструмент продуктов обратился к сайту банка")


eldik_client._cached_get = _no_network

# --- карты ------------------------------------------------------------------

r = tools.list_card_products()
check("пустой query: только карты для физлиц (8 из 10)", r["count"] == 8)
check("бизнес-карты скрыты по умолчанию",
      all(i["audience"] == "individual" for i in r["items"]))

r = tools.list_card_products("бизнес")
check("запрос про бизнес показывает бизнес-карту", "ЭЛКАРТ Бизнес" in names(r))

r = tools.list_card_products("visa gold")
gold = r["items"][0] if r["count"] else {}
check("'visa gold' -> ровно одна карта", r["count"] == 1 and gold.get("name") == "Visa Gold")
check("условия Visa Gold (500 сом) доходят до агента через details",
      "500 сом" in gold.get("details", ""))
check("annual_service_cost остаётся None, а не 'бесплатно'",
      gold.get("annual_service_cost") is None)
check("у карты есть источник и дата",
      gold.get("official_page", "").endswith("/visa-gold") and gold.get("data_date") == "2026-01-01")
check("файл тарифов Mastercard не прикреплён к Visa Gold (продукты не смешиваются)",
      not any("Тарифы" in (d["title"] or "") for d in gold.get("documents", [])))

r = tools.list_card_products("world elite")
we = r["items"][0] if r["count"] else {}
check("World Elite: обслуживание 10 000 сом из данных", we.get("annual_service_cost") == "10 000 сом")
check("World Elite теперь с подробными условиями (без пометки 'только список')", "data_level" not in we)
vi = tools.list_card_products("visa infinite")["items"][0]
check("Visa Infinite: обслуживание 10 000 сом, переводы в другие банки 1 % в тексте",
      vi.get("annual_service_cost") == "10 000 сом" and "минимум 150 сом" in vi["details"])
check("Visa Infinite: PDF с тарифами и правилами среди документов",
      any("tariffs" in d["url"] for d in vi["documents"]) and any("Rules" in d["url"] for d in vi["documents"]))

for q in ("mastercard", "мастеркард"):
    check(f"'{q}' находит Mastercard-карты (кириллическая 'с' на сайте)",
          {"Mastercard Gold", "Mastercard World Elite"} <= set(names(tools.list_card_products(q))))

for q in ("элкарт", "элкард", "Elcard"):
    check(f"'{q}' -> карты ЭЛКАРТ",
          any("ЭЛКАРТ" in n for n in names(tools.list_card_products(q))))

check("'пенсионер' -> карта пенсионера",
      "ЭЛКАРТ - Карта пенсионера" in names(tools.list_card_products("для пенсионера")))

r = tools.list_card_products("zzzxxy")
check("выдуманный запрос: 0 результатов и подсказка не выдумывать",
      r["count"] == 0 and "Не выдумывай" in r["hint"])

# --- кредиты и депозиты -----------------------------------------------------------

r = tools.list_credit_products()
check("все 16 кредитных продуктов доступны", r["count"] == 16)

r = tools.list_credit_products("кредит на авто")
check("'кредит на авто' -> Авто в кредит первым", names(r)[:1] == ["Авто в кредит"])
auto = r["items"][0] if r["count"] else {}
check("условия кредита (ставка) переданы словарём",
      "Процентная ставка" in auto.get("conditions", {}))

r = tools.list_credit_products("ипотека")
check("'ипотека' находит ипотечные продукты", r["count"] >= 3)

r = tools.list_deposit_products("вклад для детей")
check("'вклад для детей' -> детские депозиты",
      r["count"] == 2 and all("етск" in n for n in names(r)))
check("все 8 депозитов доступны", tools.list_deposit_products()["count"] == 8)

# --- остальные разделы ----------------------------------------------------------------

r = tools.search_knowledge("как подключить мобильный банкинг")
check("мобильный банкинг: инструкция подключения первой",
      "подключить" in (names(r)[0] or "").lower())

r = tools.search_knowledge("овердрафт")
check("овердрафт найден", names(r)[:1] == ["Овердрафт"])

r = tools.search_knowledge("перевод за границу")
check("'перевод за границу' -> раздел переводов",
      r["count"] and all(i.get("section") == "transfers" for i in r["items"]))

r = tools.search_knowledge("перевод за границу")
check("привилегии карт не примешиваются к общему поиску про переводы",
      all(i.get("section") != "card_privileges" for i in r["items"]))
r = tools.search_knowledge("зарплатный проект")
check("привилегии карт не примешиваются к зарплатному проекту",
      all(i.get("section") != "card_privileges" for i in r["items"]))

r = tools.search_knowledge("western union")
check("Western Union найден", names(r) == ["Western Union"])

r = tools.search_knowledge("мурабаха авто")
check("исламские продукты найдены",
      r["count"] and all(i.get("section") == "islamic" for i in r["items"]))

check("зарплатный проект найден",
      tools.search_knowledge("зарплатный проект")["items"][0]["section"] == "salary_project")

r = tools.search_knowledge("оферта договора банковского дистанционного обслуживания")
check("юридические тексты не попадают в поиск",
      all(i.get("section") != "legal" for i in r.get("items", [])))

r = tools.search_knowledge("zzzxxy")
check("search_knowledge: неизвестный запрос -> hint", r["count"] == 0 and "hint" in r)

r = tools.search_bank_products("visa")
check("search_bank_products больше не падает на картах",
      r.get("count", 0) >= 2 and "error" not in r)
r = tools.search_bank_products("расскажи пожалуйста")
check("слишком общий запрос -> обзор разделов", "overview" in r)

# --- банкоматы, отделения, кассы ---------------------------------------------------

r = tools.find_locations("Бишкек", "atm")
check("банкоматы Бишкека найдены (70 в данных)", r["total"] == 70 and r["shown"] <= 8)
check("в результате нет статуса и графика работы (их нет в данных)",
      all(not ({"status", "is_open", "hours", "working_hours"} & set(i)) for i in r["items"]))
check("ссылку на карту строит код", all(i.get("map_link", "").startswith("https://www.google.com/maps?q=")
                                       for i in r["items"] if "map_link" in i))

r = tools.find_locations("Ош", "branch")
check("отделения в Оше найдены", r["total"] >= 1 and all("Ош" in (i["region"] or "") + (i["city"] or "") + i["address"] for i in r["items"]))

r = tools.find_locations("Ош", "atm")
check("банкоматов в Оше в данных нет: 0 результатов, подсказка и coverage",
      r["total"] == 0 and "hint" in r and list(r["coverage"]) == ["г. Бишкек"])

r = tools.find_locations("")
check("пустой запрос: все типы, не больше 8 за раз", r["total"] > 100 and r["shown"] == 8)
check("выдуманный город: 0 результатов", tools.find_locations("Атлантида")["total"] == 0)

# --- инструкция по смене PIN -------------------------------------------------------

r = tools.search_knowledge("как поменять пин", "instructions")
pin = r["items"][0] if r["count"] else {}
check("инструкция по смене PIN найдена", pin.get("title") == "Как сменить ПИН-код карты")
check("в инструкции три способа и шаги банкомата",
      all(w in pin.get("text", "") for w in ("В приложении", "В банкомате", "В отделении", "Введите старый ПИН-код")))
check("инструкция по PIN не подмешивается к картам",
      all(i.get("name") != "Как сменить ПИН-код карты" for i in tools.list_card_products()["items"]))
r = tools.search_knowledge("смена пин-кода карты")
check("поиск без раздела тоже находит инструкцию по PIN",
      any(i.get("title") == "Как сменить ПИН-код карты" for i in r.get("items", [])))

# --- привилегии премиальной карты (World Elite) ----------------------------------------

r = tools.search_knowledge("как пользоваться бизнес-залом LoungeKey", "card_privileges")
lounge = r["items"][0] if r["count"] else {}
check("LoungeKey: найдена отдельная запись привилегии",
      "LoungeKey" in lounge.get("title", "") and "Mastercard Airport Experiences" in lounge.get("text", ""))
check("LoungeKey: нюансы (зависит от аэропорта, остаток 1 USD) не потеряны",
      "терминала" in lounge.get("text", "") and "1 USD" in lounge.get("text", ""))
r = tools.search_knowledge("Fast Track как оформить")
check("Fast Track находится и без указания раздела",
      any("Fast Track" in i.get("title", "") for i in r.get("items", [])))
r = tools.search_knowledge("страховка World Elite", "card_privileges")
ins = next((i for i in r.get("items", []) if "Страхование" in i.get("title", "")), {})
check("страховка: названы лимиты по пунктам и расхождение с шапкой страницы",
      "500 000 USD" in ins.get("text", "") and "1 500 000" in ins.get("text", ""))
check("привилегии не появляются в списке карт",
      all("Страхование" not in (i.get("name") or "") for i in tools.list_card_products()["items"]))
we = tools.list_card_products("World Elite")["items"][0]
check("World Elite: условия и PDF с тарифами в карточке, дата данных не пустая",
      "120 $" in we["details"] and any("pdf" in d["url"].lower() for d in we["documents"]) and we.get("data_date"))

# --- сроки программ Visa Infinite (сравниваются с сегодняшней датой) ---------------------

from datetime import date  # noqa: E402

_real_today = tools._today
tools._today = lambda: date(2026, 10, 15)

r = tools.search_knowledge("Fast Track Visa Infinite", "card_privileges")
ft = next((i for i in r["items"] if "Infinite" in i.get("title", "")), {})
check("Fast Track Visa Infinite: срок 30.09.2026 истёк, есть предупреждение",
      "validity_warning" in ft and "30.09.2026" in ft["validity_warning"])
r = tools.search_knowledge("скидки партнёры Visa Infinite", "card_privileges")
offers = next((i for i in r["items"] if "Скидки" in i.get("title", "")), {})
check("скидки: истёкшие предложения отделены от действующих",
      any("Airalo" in e for e in offers.get("offers_expired", []))
      and all(o["partner"] != "Airalo" for o in offers.get("offers_active", []))
      and any(o["partner"] == "Avis" for o in offers.get("offers_active", [])))
check("в ответе есть сегодняшняя дата для сравнения", offers.get("today") == "2026-10-15")

tools._today = lambda: date(2026, 9, 1)
r = tools.search_knowledge("Fast Track Visa Infinite", "card_privileges")
ft = next((i for i in r["items"] if "Infinite" in i.get("title", "")), {})
check("до окончания срока предупреждения нет, показана дата окончания",
      "validity_warning" not in ft and ft.get("valid_until") == "30.09.2026")
tools._today = _real_today

r = tools.search_knowledge("VIP зал Манас")
check("VIP-зал «Манас»: находится без указания раздела, с условием 80 000 сомов",
      any("80 000" in i.get("text", "") for i in r.get("items", [])))
r = tools.search_knowledge("страховка Visa Infinite", "card_privileges")
ins = next((i for i in r["items"] if "медицинская" in i.get("title", "")), {})
check("страховка Infinite: названы обе суммы (1 млн и 2,5 млн USD)",
      "1 млн" in ins.get("text", "") and "2,5 млн" in ins.get("text", ""))

# --- тарифы -----------------------------------------------------------------------------

r = tools.get_tariff_documents("visa")
check("тарифы Visa: ссылки на PDF и предупреждение 'только список'",
      r["count"] >= 1 and "не называй суммы" in r["note"])

# --- устойчивость -------------------------------------------------------------------

saved = knowledge._store
knowledge._store = None
saved_dir = knowledge.DEFAULT_DIR
knowledge.DEFAULT_DIR = Path(tmp.name) / "нет_такой_папки"
r = tools.list_card_products()
check("нет базы знаний -> понятная ошибка вместо падения",
      "error" in r and "по памяти" in r["error"])
knowledge.DEFAULT_DIR = saved_dir
knowledge._store = saved

# --- расчёты (не менялись) -----------------------------------------------------

p = tools.calculate_loan_payment(500000, 20, 36)
check("аннуитет 500к/20%/36мес ≈ 18 581", abs(p["monthly_payment"] - 18581.0) < 5)
check("переплата = итого - сумма", abs(p["overpayment"] - (p["total_payment"] - 500000)) < 0.02)
check("ставка 0% -> 10 000/мес",
      tools.calculate_loan_payment(120000, 0, 12)["monthly_payment"] == 10000.0)
check("отрицательная сумма -> error", "error" in tools.calculate_loan_payment(-1, 10, 12))
check("депозит 100к/12%/12мес -> 12 000 процентов",
      tools.calculate_deposit_income(100000, 12, 12)["total_interest"] == 12000.0)

check("контакт-центр 9111 в контактах", "9111" in tools.get_bank_contacts()["contact_center"])

# --- согласованность деклараций ---------------------------------------------------

declared = {d["name"] for d in tools.TOOL_DECLARATIONS}
check("декларации инструментов == реализации", declared == set(tools.TOOL_FUNCTIONS))
check("все результаты инструментов сериализуются в JSON",
      all(json.dumps(f(), ensure_ascii=False) for f in (
          tools.list_card_products, tools.list_credit_products,
          tools.list_deposit_products, tools.get_tariff_documents)))

st = knowledge.status()
check("в статусе есть дата данных и документы",
      st["data_date"] == "2026-01-01" and st["documents"] > 50)

tmp.cleanup()
print("\nИТОГ:", "ВСЕ ТЕСТЫ ПРОШЛИ" if ok else "ЕСТЬ ПАДЕНИЯ")
sys.exit(0 if ok else 1)
