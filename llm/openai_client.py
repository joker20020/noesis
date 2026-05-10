from openai import AsyncOpenAI
from llm.base import LlmClient, LlmResponse, Message, ToolSchema, ProviderConverter, ContentBlock, ToolCall
from agent.config import LLMConfig
import json


class OpenAICompatibleConverter(ProviderConverter):
    """OpenAI-compatible format converter (works for OpenAI, DeepSeek, etc.)."""

    def to_provider(self, messages: list[Message], tools: list[ToolSchema] | None = None):
        provider_msgs = []
        for m in messages:
            for block in m.content:
                if block.type in ("text", "thinking"):
                    provider_msgs.append({
                        "role": m.role,
                        "content": block.text or block.thinking or "",
                    })
                elif block.type == "tool_use":
                    provider_msgs.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": block.id, "type": "function",
                            "function": {"name": block.name, "arguments": json.dumps(block.input or {})}
                        }]
                    })
                elif block.type == "tool_result":
                    provider_msgs.append({
                        "role": "system",
                        "content": block.output or "",
                        "tool_call_id": block.tool_call_id,
                    })

        provider_tools = None
        if tools:
            provider_tools = []
            for t in tools:
                if isinstance(t, dict):
                    provider_tools.append(t if "type" in t else {
                        "type": "function",
                        "function": {"name": t.get("name", ""), "description": t.get("description", ""), "parameters": t.get("parameters", {})}
                    })
                else:
                    provider_tools.append({
                        "type": "function",
                        "function": {"name": t.name, "description": t.description, "parameters": t.parameters}
                    })

        return provider_msgs, provider_tools

    def from_provider(self, response: dict) -> LlmResponse:
        choice = response.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = []

        if msg.get("content"):
            content.append(ContentBlock(type="text", text=msg["content"]))

        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))
            content.append(ContentBlock(
                type="tool_use", id=tc.get("id", ""),
                name=fn.get("name", ""), input=args))

        return LlmResponse(content=content, tool_calls=tool_calls)


class OpenAIClient(LlmClient):
    def __init__(self, config: LLMConfig):
        self.model = config.model
        kwargs = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**kwargs)
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature
        self._converter = OpenAICompatibleConverter()

    async def chat(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> LlmResponse:
        provider_msgs, provider_tools = self._converter.to_provider(messages, tools)
        kwargs: dict = {
            "model": self.model, "messages": provider_msgs,
            "max_tokens": self._max_tokens, "temperature": self._temperature,
        }
        if provider_tools:
            kwargs["tools"] = provider_tools

        resp = await self._client.chat.completions.create(**kwargs)
        raw = resp.model_dump()
        return self._converter.from_provider(raw)
