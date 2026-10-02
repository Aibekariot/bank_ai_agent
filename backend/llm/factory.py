"""
Factory для выбора LLM-провайдера.
"""

import os

from .base import LLMProvider
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider


def create_llm_provider(
    system_prompt: str,
    tool_declarations: list[dict],
) -> LLMProvider:

    provider = os.environ.get(
        "LLM_PROVIDER",
        "gemini",
    ).lower()

    print(
        f"[LLM] provider={provider}"
    )

    if provider == "gemini":

        return GeminiProvider(
            system_prompt=system_prompt,
            tool_declarations=tool_declarations,
        )

    if provider == "openrouter":

        return OpenRouterProvider(
            system_prompt=system_prompt,
            tool_declarations=tool_declarations,
        )

    raise ValueError(
        f"Неизвестный LLM_PROVIDER: {provider}"
    )