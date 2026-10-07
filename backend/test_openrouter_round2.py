import json
import os
import time

import httpx
from dotenv import load_dotenv

from agent import SYSTEM_PROMPT
from tools import TOOL_DECLARATIONS


load_dotenv()


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

API_KEY = os.environ["OPENROUTER_API_KEY"]

MODEL = os.environ.get(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3.5-lightning:free",
)


def convert_tools(declarations):
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in declarations
    ]


def request(client, payload, label):
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)

    started = time.perf_counter()

    response = client.post(
        OPENROUTER_URL,
        json=payload,
    )

    elapsed = time.perf_counter() - started

    print(f"HTTP status: {response.status_code}")
    print(f"Time: {elapsed:.3f}s")

    if response.status_code >= 400:
        print("ERROR:")
        print(response.text[:3000])
        return None

    data = response.json()

    print(f"Model used: {data.get('model')}")

    choices = data.get("choices", [])

    if not choices:
        print("ERROR: no choices")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:5000])
        return None

    choice = choices[0]
    message = choice.get("message", {})

    print("Finish reason:", choice.get("finish_reason"))
    print("Content:", message.get("content"))

    tool_calls = message.get("tool_calls") or []

    if tool_calls:
        print("Tool calls:")

        for call in tool_calls:
            print(
                json.dumps(
                    call,
                    ensure_ascii=False,
                    indent=2,
                )
            )

    return message


def main():
    print("OpenRouter Round 2 diagnostic test")
    print(f"Model: {MODEL}")

    tools = convert_tools(TOOL_DECLARATIONS)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": "Какой сейчас курс доллара?",
        },
    ]

    with httpx.Client(
        timeout=120.0,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    ) as client:

        # =====================================================
        # REQUEST 1
        # Просим модель выбрать инструмент.
        # =====================================================

        payload_1 = {
            "model": MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        assistant_message = request(
            client,
            payload_1,
            "REQUEST 1 — получение tool_call",
        )

        if assistant_message is None:
            return

        tool_calls = assistant_message.get("tool_calls") or []

        if not tool_calls:
            print("\nМодель не вернула tool_call.")
            print("Невозможно провести тест второго раунда.")
            return

        # Добавляем ответ assistant в историю.
        messages.append(assistant_message)

        # =====================================================
        # Имитируем результат реального get_exchange_rate
        # =====================================================

        tool_call = tool_calls[0]

        fake_result = {
            "currency": "USD",
            "date": "2026-10-06",
            "rate_buy": 87.50,
            "rate_sell": 87.80,
        }

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(
                    fake_result,
                    ensure_ascii=False,
                ),
            }
        )

        print("\n" + "=" * 70)
        print("Имитируем результат get_exchange_rate")
        print("=" * 70)
        print(
            json.dumps(
                fake_result,
                ensure_ascii=False,
                indent=2,
            )
        )

        # =====================================================
        # REQUEST 2
        # Самая важная часть теста.
        #
        # Модель получает:
        # SYSTEM_PROMPT
        # USER
        # ASSISTANT TOOL CALL
        # TOOL RESULT
        #
        # И должна сформировать финальный ответ.
        # =====================================================

        payload_2 = {
            "model": MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        request(
            client,
            payload_2,
            "REQUEST 2 — ответ после tool result",
        )


if __name__ == "__main__":
    main()