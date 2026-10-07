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
    """
    Преобразует наши TOOL_DECLARATIONS
    в формат OpenAI/OpenRouter function calling.

    Это точно такой же формат, который
    используется в backend/llm/openrouter.py.
    """
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


def make_request(name, system_prompt, tools=None):
    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": "Какой сейчас курс доллара?",
            },
        ],
    }

    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    started = time.perf_counter()

    try:
        with httpx.Client(
            timeout=120.0,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
        ) as client:
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
            return

        data = response.json()

        print(f"Model used: {data.get('model')}")

        choices = data.get("choices", [])

        if not choices:
            print("ERROR: OpenRouter returned no choices")
            print(json.dumps(data, ensure_ascii=False, indent=2)[:5000])
            return

        choice = choices[0]
        message = choice.get("message", {})

        print("Finish reason:", choice.get("finish_reason"))
        print("Content:", message.get("content"))

        tool_calls = message.get("tool_calls") or []

        if tool_calls:
            print("\nTool calls:")

            for call in tool_calls:
                print(
                    json.dumps(
                        call,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

    except Exception as exc:
        elapsed = time.perf_counter() - started

        print(f"ERROR after {elapsed:.3f}s:")
        print(type(exc).__name__, exc)


def main():
    print("OpenRouter diagnostic test")
    print(f"Model: {MODEL}")

    converted_tools = convert_tools(TOOL_DECLARATIONS)

    print(f"Tools count: {len(converted_tools)}")

    # =========================================================
    # TEST 1
    # Простой system prompt.
    # Без tools.
    # =========================================================

    make_request(
        "TEST 1 — простой prompt, без tools",
        "Ты банковский помощник. Отвечай кратко.",
    )

    # =========================================================
    # TEST 2
    # Настоящий SYSTEM_PROMPT.
    # Без tools.
    # =========================================================

    make_request(
        "TEST 2 — настоящий SYSTEM_PROMPT, без tools",
        SYSTEM_PROMPT,
    )

    # =========================================================
    # TEST 3
    # Настоящий SYSTEM_PROMPT + tools.
    # Формат tools такой же, как в OpenRouterProvider.
    # =========================================================

    make_request(
        "TEST 3 — настоящий SYSTEM_PROMPT + все tools",
        SYSTEM_PROMPT,
        converted_tools,
    )


if __name__ == "__main__":
    main()