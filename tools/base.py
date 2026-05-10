from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    success: bool
    output: str
    error: str | None = None


class BaseTool(ABC):

    @abstractmethod
    def schema(self) -> ToolSchema:
        ...

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        ...

    @property
    def name(self) -> str:
        return self.schema().name
