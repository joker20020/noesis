from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LlmResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]


class LlmClient(ABC):

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
    ) -> LlmResponse:
        ...
