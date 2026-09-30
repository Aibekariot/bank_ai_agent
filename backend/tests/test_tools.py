import sys, types, json
# httpx может быть не установлен в песочнице - заглушка (сеть всё равно не используем)
try:
    import httpx  # noqa
except ImportError:
    sys.modules["httpx"] = types.ModuleType("httpx")

import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import eldik_client, tools

# --- фикстуры в формате реальных ответов сайта (сокращено) ---
def card(name, cat, ps, cur, iss=None, ann=None, desc="", creatable=True):
    return {"name": name, "slug": name.lower(), "description": desc, "category": cat,
            "payment_system": ps, "currencies": cur, "issuance_cost": iss,
            "annual_service_cost": ann, "validity": "5 лет", "available": True,
            "online_order_available": creatable}

CARDS = [
  card("Mastercard World Elite","Премиум","Masterсard",["USD","СОМ"],None,"10 000 сом",
       "Премиальная карта: бизнес-залы, Fast Track, кешбэк 2%",False),
  card("Виртуальные карты","Виртуальные карты","Виртуальные карты",["USD","СОМ","EUR"],"Бесплатно","Бесплатно","Электронный аналог карты",False),
  card("ЭЛКАРТ - Бесконтакт","Дебетовые карты","Элкарт",["СОМ"],"350 сом",None,"Бесконтактная карта национальной системы"),
  card("ЭЛКАРТ - Карта пенсионера","Дебетовые карты","Элкарт",["СОМ"],None,"Бесплатно","Карта для пенсий и пособий"),
  card("Visa Gold","Дебетовые карты","Visa",["USD","СОМ","EUR"],"Бесплатно",None,"Международная карта, повышенные лимиты"),
  card("Visa Business","Бизнес","Visa",["СОМ","USD"],"Бесплатно",None,"Для юрлиц и ИП",False),
  card("Mastercard Gold","Премиум","Masterсard",["СОМ","USD","EUR"],"Бесплатно",None,"Международная платежная карта"),
]
CREDITS = [
  {"name":"Потребительское кредитование","slug":"p","description":"Кредит на любые цели","conditions":{"Процентная ставка":"от 20%","Срок кредита":"до 60 месяцев"}},
  {"name":"Авто в кредит","slug":"a","description":"Мечтаешь о машине?","conditions":{"Процентная ставка":"от 19% годовых","Сумма кредита":"до 4 000 000 сом"}},
  {"name":"Кредитная карта","slug":"k","description":"Универсальный платежный инструмент","conditions":{"Ставка":"0,0767 % в день"}},
]
DEPOSITS = [
  {"name":"Срочный депозит «Сандык»","slug":"s","description":"Ваши сбережения под защитой","conditions":{"Ставка":"до 14% годовых"}},
  {"name":"Депозит «Капитал Стандарт»","slug":"c","description":"Недоступен для новых клиентов. Действующие клиенты обслуживаются","conditions":{"Ставка":"до 11% годовых"}},
]
eldik_client.get_cards = lambda: CARDS
eldik_client.get_credits = lambda: CREDITS
eldik_client.get_deposits = lambda: DEPOSITS

def names(res, key): return [p["name"] for p in res.get(key, [])]
ok = True
def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label); ok &= bool(cond)

# 1. "карта" -> обзор категории карт + подсказка уточнить
r = tools.search_bank_products("карта")
check("'карта' -> вернулись все 7 карт", len(r.get("cards", [])) == 7)
check("'карта' -> есть hint про уточнение", "hint" in r)
check("'карта' -> не тянет кредиты/депозиты", "credits" not in r and "deposits" not in r)

# 2. "карты" (множественное)
check("'карты' -> тоже обзор карт", len(tools.search_bank_products("карты").get("cards", [])) == 7)

# 3. конкретика: "visa"
r = tools.search_bank_products("visa")
check("'visa' -> Visa Gold и Visa Business", set(names(r,"cards")) == {"Visa Gold","Visa Business"})

# 4. кириллица-двойник: 'mastercard' находит 'Masterсard' с русской с
r = tools.search_bank_products("mastercard")
check("'mastercard' находит карты несмотря на кириллическую 'с' на сайте",
      {"Mastercard World Elite","Mastercard Gold"} <= set(names(r,"cards")))

# 5. русское написание
r = tools.search_bank_products("мастеркард")
check("'мастеркард' -> Mastercard-карты", {"Mastercard Gold"} <= set(names(r,"cards")))

# 6. пенсионер (кросс-категорийно, без слова 'карта')
r = tools.search_bank_products("что есть для пенсионера")
check("'для пенсионера' -> карта пенсионера", "ЭЛКАРТ - Карта пенсионера" in names(r,"cards"))

# 7. элкарт разными написаниями
for q in ["элкарт","Elcard","элкард"]:
    r = tools.search_bank_products(q)
    check(f"'{q}' -> ЭЛКАРТ", any("ЭЛКАРТ" in n for n in names(r,"cards")))

# 8. кредит на авто
r = tools.search_bank_products("хочу кредит на авто")
check("'кредит на авто' -> Авто в кредит", "Авто в кредит" in names(r,"credits"))
check("'кредит на авто' -> не возвращает карты", "cards" not in r)

# 9. вклад
r = tools.search_bank_products("вклад")
check("'вклад' -> обзор депозитов", len(r.get("deposits", [])) == 2)

# 10. пустой/шумовой запрос
r = tools.search_bank_products("расскажи пожалуйста")
check("шумовой запрос -> overview + hint", "overview" in r and "hint" in r)

# 11. нет совпадений
r = tools.search_bank_products("ипотека на луне xyzzy")
check("выдуманный запрос не даёт мусор (нет карт/депозитов)", "cards" not in r and "deposits" not in r)

# 12. фильтры list_*
check("list_card_products('премиум') -> 2 карты", len(tools.list_card_products("премиум")) == 2)
check("list_card_products() без фильтра -> все", len(tools.list_card_products()) == 7)

# 13. депозит с пометкой недоступности сохраняет описание
d = tools.list_deposit_products("капитал")
check("описание 'Недоступен для новых клиентов' доходит до агента",
      d and "Недоступен для новых клиентов" in d[0]["description"])

# 14. null-стоимость не превращается в 'бесплатно'
c = tools.list_card_products("elkart")[0] if tools.list_card_products("elkart") else None
check("null годового обслуживания остаётся None", c is not None and c["annual_service_cost"] is None)

# 15. расчёты
p = tools.calculate_loan_payment(500000, 20, 36)
check("аннуитет 500к/20%/36мес ≈ 18 581", abs(p["monthly_payment"] - 18581.0) < 5)
check("переплата = итого - сумма", abs(p["overpayment"] - (p["total_payment"]-500000)) < 0.02)
p0 = tools.calculate_loan_payment(120000, 0, 12)
check("ставка 0% -> 10 000/мес", p0["monthly_payment"] == 10000.0)
check("отрицательная сумма -> error", "error" in tools.calculate_loan_payment(-1, 10, 12))
dep = tools.calculate_deposit_income(100000, 12, 12)
check("депозит 100к/12%/12мес -> 12 000 процентов", dep["total_interest"] == 12000.0)

# 16. контакты и очистка HTML
check("контакт-центр 9111 в контактах", "9111" in tools.get_bank_contacts()["contact_center"])
check("_clean_html чистит теги и entities",
      eldik_client._clean_html("<p>Карта &laquo;Элдик&raquo;&nbsp;Gold</p>") == "Карта «Элдик» Gold")

# 17. все объявленные tools реализованы
declared = {d["name"] for d in tools.TOOL_DECLARATIONS}
check("декларации == реализации", declared == set(tools.TOOL_FUNCTIONS))

print("\nИТОГ:", "ВСЕ ТЕСТЫ ПРОШЛИ" if ok else "ЕСТЬ ПАДЕНИЯ")
