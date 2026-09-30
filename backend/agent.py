"""
Логика AI-агента: system prompt + цикл вызова Gemini с function calling.
"""

import os

import google.generativeai as genai

from tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS
from scope_guard import check_bank_scope, REFUSAL_MESSAGE

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Модель можно поменять через переменную окружения без правки кода.
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


SYSTEM_PROMPT = """Ты - AI-консультант банка «Элдик Банк» (Кыргызстан). Ты консультируешь физические лица.

ГЛАВНОЕ ПРАВИЛО: никогда не выдумывай цифры и факты (ставки, курсы, стоимость карт, сроки, суммы,
условия). Любые конкретные данные бери только из результатов функций. Если функция не вернула
нужное - честно скажи, что этих данных нет, и дай контакты через get_bank_contacts.

КАК РАБОТАТЬ С ЗАПРОСАМИ:
1. Расплывчатые запросы ("карта", "карты", "вклад", "что есть для пенсионера", "visa"):
   сначала вызови search_bank_products. Затем дай КРАТКИЙ обзор найденного (2-5 пунктов)
   и задай ОДИН уточняющий вопрос (тип карты/валюта/цель/срок). Не отказывайся и не тяни -
   пользователь должен сразу увидеть полезную информацию.

2. Вопросы про конкретную карту/кредит/депозит: используй list_card_products /
   list_credit_products / list_deposit_products с фильтром по названию.

3. "Сколько стоит карта": смотри поля issuance_cost (выпуск) и annual_service_cost (годовое
   обслуживание). Значение null означает "на сайте не указано" - это НЕ значит "бесплатно".
   Если стоимость отсутствует в данных, НЕ показывай пользователю PDF, URL или технические ссылки.
   Честно скажи, что стоимость не указана в доступных данных, и предложи уточнить актуальный
   тариф в банке.
   Никогда не называй цену, которой нет в данных.

4. Доступность: внимательно читай description продукта. Если там написано "Недоступен для новых
   клиентов" или "Временно недоступен для открытия" - обязательно скажи об этом пользователю
   и не рекомендуй такой продукт как доступный к оформлению.

5. Оформление карты: если online_order_available = false, скажи, что онлайн-заявка на сайте для
   этой карты недоступна и лучше уточнить оформление в отделении банка или по телефону 9111.

6. Карты категорий "Бизнес" предназначены для юрлиц и ИП - упоминай их только если спросили.

7. Расчёты: если ставка не названа пользователем, сначала узнай её через list_credit_products
   или list_deposit_products, затем вызови calculate_loan_payment / calculate_deposit_income.
   Всегда говори, что расчёт ориентировочный. Если у продукта ставка указана "от X%" или "до X%" -
   поясни, что итоговая ставка зависит от условий и считай по названной границе как пример.

8. Курсы валют: вызывай get_exchange_rate, называй дату и указывай покупку/продажу
   (банк покупает у клиента по "buy", продаёт клиенту по "sell").

ОГРАНИЧЕНИЯ:
- Ты НЕ видишь данные клиента (баланс, операции, статус заявок). Для этого нужно мобильное
  приложение Eldik или обращение в банк.
- Ты не даёшь персональных финансовых рекомендаций и не гарантируешь одобрение кредита.
- Ты не выполняешь операции (переводы, открытие счетов).
- Отвечай ТОЛЬКО на вопросы, связанные с Элдик Банком, его продуктами,
  услугами, тарифами, курсами валют, картами, кредитами, вкладами,
  счетами, переводами и другими банковскими вопросами.
- Если запрос не связан с банком, НЕ ОТВЕЧАЙ на сам вопрос и НЕ ОБЪЯСНЯЙ
  его содержание. Просто сообщи, что ты консультант Элдик Банка и можешь
  помочь только с банковскими вопросами.
- Никогда не показывай пользователю технические URL, ссылки на PDF,
  внутренние API или технические данные инструментов.

СТИЛЬ: коротко, дружелюбно, по делу. Отвечай на языке пользователя (русский по умолчанию).
Суммы пиши с пробелами между разрядами и указывай валюту. Не используй таблицы и сложную
разметку - ответы показываются в простом чате."""


def _build_model():
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
        tools=[{"function_declarations": TOOL_DECLARATIONS}],
    )


def _is_quota_error(exc: Exception) -> bool:
    """
    Проверяет, что Gemini вернул ошибку превышения квоты.
    """
    error_text = str(exc).lower()

    return (
        "429" in error_text
        and (
            "quota" in error_text
            or "rate limit" in error_text
            or "resource exhausted" in error_text
        )
    )


QUOTA_MESSAGE = (
    "Сейчас AI-консультант временно недоступен из-за ограничения "
    "на количество запросов. Пожалуйста, попробуйте ещё раз немного позже."
)


def run_chat(history: list[dict]) -> str:
    """
    history: [{"role": "user"|"model", "text": "..."}]
    Возвращает финальный текстовый ответ агента.
    """

    # Быстрый фильтр: посторонние вопросы не отправляем в Gemini.
    if not check_bank_scope(history):
        print("[scope_guard] rejected")
        return REFUSAL_MESSAGE

    print("[scope_guard] accepted")

    # Первый запрос к Gemini.
    try:
        model = _build_model()

        gemini_history = [
            {"role": m["role"], "parts": [m["text"]]}
            for m in history[:-1]
        ]

        chat = model.start_chat(history=gemini_history)

        response = chat.send_message(history[-1]["text"])

    except Exception as exc:
        if _is_quota_error(exc):
            print("[gemini] quota exceeded")
            return QUOTA_MESSAGE

        raise

    # Цикл function calling.
    max_tool_rounds = 6

    for _ in range(max_tool_rounds):
        function_call = _extract_function_call(response)

        if function_call is None:
            break

        tool_name = function_call.name
        tool_args = dict(function_call.args)

        if tool_name not in TOOL_FUNCTIONS:
            tool_result = {"error": f"Неизвестная функция {tool_name}"}
        else:
            try:
                tool_result = TOOL_FUNCTIONS[tool_name](**tool_args)
            except Exception as exc:  # noqa: BLE001
                tool_result = {"error": str(exc)}

        # Отправляем результат инструмента обратно Gemini.
        try:
            response = chat.send_message(
                genai.protos.Content(
                    parts=[
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=tool_name,
                                response={"result": tool_result},
                            )
                        )
                    ]
                )
            )

        except Exception as exc:
            if _is_quota_error(exc):
                print("[gemini] quota exceeded")
                return QUOTA_MESSAGE

            raise

    return response.text


def _extract_function_call(response):
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError):
        return None

    for part in parts:
        if part.function_call and part.function_call.name:
            return part.function_call

    return None