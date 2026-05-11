"""DeepSeek client — AgentScope-compatible formatter.

Reference: https://github.com/agentscope-ai/agentscope/blob/main/src/agentscope/formatter/_deepseek_formatter.py
"""
import json, httpx, uuid
from llm.base import (
    LlmClient, LlmResponse, Message, ContentBlock, ToolCall, ToolSchema,
    ProviderConverter,
)
from agent.config import LLMConfig


def _ensure_tool_id(raw_id: str | None) -> str:
    return raw_id if raw_id else f"call_{uuid.uuid4().hex[:16]}"


class DeepSeekConverter(ProviderConverter):
    """DeepSeek-compatible converter.

    Strategy (aligned with AgentScope):
    - Process each Message independently.
    - tool_result blocks are emitted immediately as separate "tool" role messages.
    - tool_use blocks are collected into tool_calls on the same assistant message.
    - text / thinking are joined into content / reasoning_content.
    - A message is kept if it has non-empty content OR tool_calls.
    """

    def to_provider(self, messages: list[Message], tools: list[ToolSchema] | None = None):
        provider_msgs: list[dict] = []

        for m in messages:
            content_blocks: list[dict] = []
            reasoning_content_blocks: list[dict] = []
            tool_calls: list[dict] = []

            for block in m.content:
                if block.type == "text":
                    content_blocks.append({"text": block.text or ""})
                elif block.type == "thinking":
                    reasoning_content_blocks.append({"thinking": block.thinking or ""})
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": _ensure_tool_id(block.id),
                        "type": "function",
                        "function": {
                            "name": block.name or "",
                            "arguments": json.dumps(
                                block.input or {},
                                ensure_ascii=False,
                            ),
                        },
                    })
                elif block.type == "tool_result":
                    provider_msgs.append({
                        "role": "tool",
                        "tool_call_id": _ensure_tool_id(block.tool_call_id),
                        "content": str(block.output or ""),
                        "name": block.name or "",
                    })

            content_msg = "\n".join(
                c.get("text", "") for c in content_blocks
            )
            reasoning_msg = "\n".join(
                r.get("thinking", "") for r in reasoning_content_blocks
            )

            msg_deepseek: dict = {
                "role": m.role,
                "content": content_msg or None,
            }

            if reasoning_msg:
                msg_deepseek["reasoning_content"] = reasoning_msg

            if tool_calls:
                msg_deepseek["tool_calls"] = tool_calls
                # DeepSeek requires reasoning_content when tool_calls exist
                if "reasoning_content" not in msg_deepseek:
                    msg_deepseek["reasoning_content"] = ""

            # Keep the message if it has content or tool_calls.
            # Pure tool_result messages are already emitted above and will
            # naturally drop here because content is None and tool_calls is empty.
            if msg_deepseek["content"] or msg_deepseek.get("tool_calls"):
                provider_msgs.append(msg_deepseek)

        provider_tools = None
        if tools:
            provider_tools = []
            for t in tools:
                if isinstance(t, dict):
                    if "type" in t:
                        provider_tools.append(t)
                    else:
                        provider_tools.append({
                            "type": "function",
                            "function": {
                                "name": t.get("name", ""),
                                "description": t.get("description", ""),
                                "parameters": t.get("parameters", {}),
                            }
                        })
                else:
                    provider_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }
                    })

        return provider_msgs, provider_tools

    def from_provider(self, response: dict) -> LlmResponse:
        choice = response.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content: list[ContentBlock] = []

        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            content.append(ContentBlock(type="thinking", thinking=reasoning))

        text = msg.get("content") or ""
        content.append(ContentBlock(type="text", text=text))

        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments", ""), str) else fn.get("arguments", {})
            except (json.JSONDecodeError, TypeError):
                args = {}
            tc_id = _ensure_tool_id(tc.get("id"))
            tool_calls.append(ToolCall(id=tc_id, name=fn.get("name", ""), arguments=args))
            # Do NOT add tool_use to content blocks — conscious.py already
            # appends them from response.tool_calls separately.

        return LlmResponse(content=content, tool_calls=tool_calls)


class DeepSeekClient(LlmClient):
    def __init__(self, config: LLMConfig):
        self.model = config.model
        self.base_url = config.base_url or "https://api.deepseek.com"
        self._api_key = config.api_key
        self._max_tokens = config.max_tokens
        self._reasoning_effort = config.reasoning_effort
        self._converter = DeepSeekConverter()

    async def chat(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> LlmResponse:
        provider_msgs, provider_tools = self._converter.to_provider(messages, tools)
        body: dict = {
            "model": self.model,
            "messages": provider_msgs,
            "max_tokens": self._max_tokens,
            "reasoning_effort": self._reasoning_effort,
            "thinking": {"type": "enabled"},
        }
        if provider_tools:
            body["tools"] = provider_tools

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=body)
            if resp.status_code >= 400:
                print(f"[DeepSeek] {resp.status_code}: {resp.text[:200]}")
                for i, m in enumerate(provider_msgs):
                    if m.get("tool_calls"):
                        next_msg = provider_msgs[i + 1] if i + 1 < len(provider_msgs) else {}
                        print(f"[DeepSeek] msg[{i}]: tool_calls ids={[tc['id'] for tc in m['tool_calls']]} next_role={next_msg.get('role')} next_tcid={next_msg.get('tool_call_id')}")
            resp.raise_for_status()
            return self._converter.from_provider(resp.json())
