"""
Общий интерфейс LLM-провайдеров.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall]


class LLMProvider(ABC):

    @abstractmethod
    def start_chat(
        self,
        history: list[dict],
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def send_tool_results(
        self,
        tool_results: list[dict],
    ) -> LLMResponse:
        raise NotImplementedError