"""
OpenRouter LLM provider.

Использует OpenAI-compatible Chat Completions API.
"""

import json
import os
import time

import httpx

from .base import LLMProvider, LLMResponse, ToolCall


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODEL = "nvidia/nemotron-3-ultra:free"


class OpenRouterProvider(LLMProvider):

    def __init__(
        self,
        system_prompt: str,
        tool_declarations: list[dict],
    ):
        self.api_key = os.environ["OPENROUTER_API_KEY"]

        self.model = os.environ.get(
            "OPENROUTER_MODEL",
            DEFAULT_MODEL,
        )

        self.system_prompt = system_prompt

        self.tools = self._convert_tools(
            tool_declarations
        )

        self.messages: list[dict] = []

        self.request_number = 0

        self.client = httpx.Client(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    # ---------------------------------------------------------
    # Gemini format -> OpenRouter format
    # ---------------------------------------------------------

    @staticmethod
    def _convert_tools(
        declarations: list[dict],
    ) -> list[dict]:

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

    # ---------------------------------------------------------
    # HTTP request
    # ---------------------------------------------------------

    def _request(self) -> LLMResponse:

        self.request_number += 1

        request_number = self.request_number

        payload = {
            "model": self.model,
            "messages": self.messages,
            "tools": self.tools,
            "tool_choice": "auto",
        }

        started = time.perf_counter()

        response = self.client.post(
            OPENROUTER_URL,
            json=payload,
        )

        elapsed = time.perf_counter() - started

        print(
            f"[LLM] OpenRouter request #{request_number}: "
            f"{elapsed:.3f}s"
        )

        if response.status_code >= 400:
            print(
                "[LLM] OpenRouter error:",
                response.text[:2000],
            )

        response.raise_for_status()

        data = response.json()

        print(
            f"[LLM] OpenRouter model used: "
            f"{data.get('model')}"
        )

        choice = data["choices"][0]
        message = choice["message"]

        # Сохраняем ответ assistant.
        self.messages.append(message)

        tool_calls = []

        for call in message.get("tool_calls") or []:

            arguments_raw = call["function"].get(
                "arguments",
                "{}",
            )

            try:
                arguments = json.loads(arguments_raw)

            except json.JSONDecodeError as exc:

                raise ValueError(
                    "OpenRouter вернул некорректный "
                    f"JSON аргументов для "
                    f"{call['function']['name']}: "
                    f"{arguments_raw}"
                ) from exc

            tool_calls.append(
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=arguments,
                )
            )

        return LLMResponse(
            text=message.get("content"),
            tool_calls=tool_calls,
        )

    # ---------------------------------------------------------
    # Начало разговора
    # ---------------------------------------------------------

    def start_chat(
        self,
        history: list[dict],
    ) -> LLMResponse:

        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

        for message in history[:-1]:

            if message["role"] == "user":

                self.messages.append(
                    {
                        "role": "user",
                        "content": message["text"],
                    }
                )

            elif message["role"] == "model":

                self.messages.append(
                    {
                        "role": "assistant",
                        "content": message["text"],
                    }
                )

        # Последний user message
        self.messages.append(
            {
                "role": "user",
                "content": history[-1]["text"],
            }
        )

        return self._request()

    # ---------------------------------------------------------
    # Результаты tools
    # ---------------------------------------------------------

    def send_tool_results(
        self,
        tool_results: list[dict],
    ) -> LLMResponse:

        for result in tool_results:

            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": json.dumps(
                        result["result"],
                        ensure_ascii=False,
                    ),
                }
            )

        return self._request()