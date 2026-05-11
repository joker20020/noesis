from openai import AsyncOpenAI
from llm.base import LlmClient, LlmResponse, Message, ToolSchema, ProviderConverter, ContentBlock, ToolCall
from agent.config import LLMConfig
import json, uuid


def _ensure_tool_id(raw_id: str | None) -> str:
    return raw_id if raw_id else f"call_{uuid.uuid4().hex[:16]}"


class OpenAICompatibleConverter(ProviderConverter):
    """OpenAI-compatible format converter (works for OpenAI, DeepSeek, etc.)."""

    def to_provider(self, messages: list[Message], tools: list[ToolSchema] | None = None):
        provider_msgs: list[dict] = []
        pending_tool_uses: list[ContentBlock] = []
        pending_tool_results: list[ContentBlock] = []

        def _flush_tools():
            """Flush accumulated tool_use + tool_result as merged messages."""
            nonlocal pending_tool_uses, pending_tool_results
            if not pending_tool_uses:
                pending_tool_results = []
                return
            provider_msgs.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": _ensure_tool_id(b.id), "type": "function",
                    "function": {"name": b.name or "", "arguments": json.dumps(b.input or {})}
                } for b in pending_tool_uses],
            })
            pending_tool_uses = []
            for b in pending_tool_results:
                provider_msgs.append({
                    "role": "tool",
                    "content": b.output or "",
                    "tool_call_id": _ensure_tool_id(b.tool_call_id),
                })
            pending_tool_results = []

        for m in messages:
            text_parts = []
            thinking_parts = []
            tool_uses = []
            tool_results = []

            for block in m.content:
                if block.type == "text" and block.text:
                    text_parts.append(block.text)
                elif block.type == "thinking" and block.thinking:
                    # OpenAI doesn't support thinking blocks natively; merge as plain text
                    thinking_parts.append(block.thinking)
                elif block.type == "tool_use":
                    tool_uses.append(block)
                elif block.type == "tool_result":
                    tool_results.append(block)

            has_normal = bool(text_parts or thinking_parts)
            has_tool_use = bool(tool_uses)
            has_tool_result = bool(tool_results)

            if m.role == "assistant" and has_tool_use and not has_normal:
                pending_tool_uses.extend(tool_uses)
                continue

            if m.role in ("system", "tool") and has_tool_result and not has_normal and not has_tool_use:
                pending_tool_results.extend(tool_results)
                continue

            _flush_tools()

            if text_parts or thinking_parts:
                provider_msgs.append({
                    "role": m.role,
                    "content": "\n".join(text_parts + thinking_parts),
                })

        _flush_tools()

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

        text = msg.get("content") or ""
        if text:
            content.append(ContentBlock(type="text", text=text))

        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                args = {}
            tc_id = _ensure_tool_id(tc.get("id"))
            tool_calls.append(ToolCall(id=tc_id, name=fn.get("name", ""), arguments=args))
            # Do NOT add tool_use to content blocks — conscious.py already
            # appends them from response.tool_calls separately.

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
