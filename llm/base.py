"""Unified message model — AgentScope-compatible: role + content (list of ContentBlock)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentBlock:
    """One block in a Message's content list. AgentScope-compatible."""
    type: str  # "text" | "thinking" | "tool_use" | "tool_result"
    text: str | None = None
    thinking: str | None = None
    # tool_use fields
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    # tool_result fields
    output: str | None = None
    tool_call_id: str | None = None
    # image (future)
    source: dict | None = None


@dataclass
class Message:
    """Unified message — AgentScope-compatible. role + content (list of ContentBlock)."""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: list[ContentBlock] = field(default_factory=list)

    @classmethod
    def text_msg(cls, role: str, text: str) -> "Message":
        return cls(role=role, content=[ContentBlock(type="text", text=text)])

    @classmethod
    def thinking_msg(cls, role: str, thinking: str) -> "Message":
        return cls(role=role, content=[ContentBlock(type="thinking", thinking=thinking)])

    @classmethod
    def tool_use_msg(cls, role: str, call_id: str, name: str, input: dict) -> "Message":
        return cls(role=role, content=[ContentBlock(type="tool_use", id=call_id, name=name, input=input)])

    @classmethod
    def tool_result_msg(cls, role: str, call_id: str, name: str, output: str) -> "Message":
        return cls(role=role, content=[ContentBlock(type="tool_result", tool_call_id=call_id, name=name, output=output)])

    def get_text(self) -> str:
        """Extract all text blocks as a single string."""
        return "\n".join(b.text for b in self.content if (b.type == "text") and b.text)

    def has_block(self, block_type: str) -> bool:
        return any(b.type == block_type for b in self.content)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LlmResponse:
    """Unified LLM response — content is a list of ContentBlock."""
    content: list[ContentBlock] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]


class LlmClient(ABC):
    """Base LLM client. Subclasses implement provider-specific conversion."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
    ) -> LlmResponse:
        ...


# ── Provider Converters ──

class ProviderConverter(ABC):
    """Convert between unified Message format and provider-specific API format."""

    @abstractmethod
    def to_provider(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> tuple:
        """Convert unified messages+tools to provider-specific (messages, tools_dict)."""

    @abstractmethod
    def from_provider(self, response: dict) -> LlmResponse:
        """Convert provider response to unified LlmResponse."""

