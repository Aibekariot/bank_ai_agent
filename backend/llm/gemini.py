"""
Gemini LLM provider.
"""

import os
import time

import google.generativeai as genai

from .base import LLMProvider, LLMResponse, ToolCall


class GeminiProvider(LLMProvider):

    def __init__(
        self,
        system_prompt: str,
        tool_declarations: list[dict],
    ):
        genai.configure(
            api_key=os.environ["GEMINI_API_KEY"]
        )

        model_name = os.environ.get(
            "GEMINI_MODEL",
            "gemini-3.8-flash",
        )

        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
            tools=[
                {
                    "function_declarations":
                        tool_declarations
                }
            ],
        )

        self.chat = None
        self.request_number = 0

    # ---------------------------------------------------------
    # Первый запрос
    # ---------------------------------------------------------

    def start_chat(
        self,
        history: list[dict],
    ) -> LLMResponse:

        gemini_history = [
            {
                "role": message["role"],
                "parts": [message["text"]],
            }
            for message in history[:-1]
        ]

        self.chat = self.model.start_chat(
            history=gemini_history
        )

        return self._send(
            history[-1]["text"]
        )

    # ---------------------------------------------------------
    # Отправка сообщения
    # ---------------------------------------------------------

    def _send(self, message) -> LLMResponse:

        self.request_number += 1

        started = time.perf_counter()

        response = self.chat.send_message(
            message
        )

        elapsed = time.perf_counter() - started

        print(
            f"[LLM] Gemini request "
            f"#{self.request_number}: "
            f"{elapsed:.3f}s"
        )

        return self._parse_response(response)

    # ---------------------------------------------------------
    # Результаты tools
    # ---------------------------------------------------------

    def send_tool_results(
        self,
        tool_results: list[dict],
    ) -> LLMResponse:

        parts = []

        for result in tool_results:

            parts.append(
                genai.protos.Part(
                    function_response=
                    genai.protos.FunctionResponse(
                        name=result["name"],
                        response={
                            "result": result["result"]
                        },
                    ),
                )
            )

        return self._send(
            genai.protos.Content(
                parts=parts
            )
        )

    # ---------------------------------------------------------
    # Разбор ответа
    # ---------------------------------------------------------

    @staticmethod
    def _parse_response(
        response,
    ) -> LLMResponse:

        try:
            parts = (
                response
                .candidates[0]
                .content
                .parts
            )

        except (AttributeError, IndexError):

            return LLMResponse(
                text=getattr(
                    response,
                    "text",
                    None,
                ),
                tool_calls=[],
            )

        tool_calls = []

        for index, part in enumerate(parts):

            function_call = getattr(
                part,
                "function_call",
                None,
            )

            if not function_call:
                continue

            if not function_call.name:
                continue

            tool_calls.append(
                ToolCall(
                    id=f"gemini_call_{index}",
                    name=function_call.name,
                    arguments=dict(
                        function_call.args
                    ),
                )
            )

        text = None

        try:
            text = response.text
        except (AttributeError, ValueError):
            pass

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
        )