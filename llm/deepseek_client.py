"""DeepSeek client — AgentScope-compatible formatter.

Reference: https://github.com/agentscope-ai/agentscope/blob/main/src/agentscope/formatter/_deepseek_formatter.py
"""
import json, httpx
from llm.base import (
    LlmClient, LlmResponse, Message, ContentBlock, ToolCall, ToolSchema,
    ProviderConverter,
)
from agent.config import LLMConfig


class DeepSeekConverter(ProviderConverter):
    """AgentScope-compatible: tool_result as separate messages, reasoning_content as top-level key."""

    def __init__(self, thinking: bool = True) -> None:
        super().__init__()
        self.thinking = thinking

    def to_provider(self, messages: list[Message], tools: list[ToolSchema] | None = None):
        provider_msgs = []
        for m in messages:
            text_blocks = [b for b in m.content if b.type == "text"]
            thinking_blocks = [b for b in m.content if b.type == "thinking"]
            tool_use_blocks = [b for b in m.content if b.type == "tool_use"]

            # Tool results go DIRECTLY to message list as separate messages
            for b in m.content:
                if b.type == "tool_result":
                    output = b.output or ""
                    provider_msgs.append({
                        "role": "tool",
                        "tool_call_id": b.tool_call_id or "",
                        "content": str(output),
                    })

            # Build content from text blocks
            content_text = "\n".join(b.text or "" for b in text_blocks) if text_blocks else ""
            reasoning_text = "\n".join(b.thinking or "" for b in thinking_blocks) if thinking_blocks else None

            # Build tool_calls
            tool_calls = None
            if tool_use_blocks:
                tool_calls = [{
                    "id": b.id or "",
                    "type": "function",
                    "function": {
                        "name": b.name or "",
                        "arguments": json.dumps(b.input or {}, ensure_ascii=False),
                    }
                } for b in tool_use_blocks]

            # Assemble message
            msg: dict = {"role": m.role, "content": content_text or ""}
            if reasoning_text:
                msg["reasoning_content"] = reasoning_text
            elif tool_calls:
                # DeepSeek requires reasoning_content when tool_calls exist
                msg["reasoning_content"] = ""
            if tool_calls:
                msg["tool_calls"] = tool_calls

            if msg.get("content") or msg.get("tool_calls"):
                provider_msgs.append(msg)
            if msg.get("reasoning_content") and self.thinking:
                provider_msgs.append(msg)

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
                            "function": {"name": t.get("name",""), "description": t.get("description",""), "parameters": t.get("parameters",{})}
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

        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            content.append(ContentBlock(type="thinking", thinking=reasoning))
        
        content.append(ContentBlock(type="text", text=msg["content"]))

        tool_calls = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments", ""), str) else fn.get("arguments", {})
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))

        return LlmResponse(content=content, tool_calls=tool_calls)


class DeepSeekClient(LlmClient):
    def __init__(self, config: LLMConfig):
        self.model = config.model
        self.base_url = config.base_url or "https://api.deepseek.com"
        self._api_key = config.api_key
        self._max_tokens = config.max_tokens
        self._converter = DeepSeekConverter()

    async def chat(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> LlmResponse:
        provider_msgs, provider_tools = self._converter.to_provider(messages, tools)
        body: dict = {
            "model": self.model, "messages": provider_msgs,
            "max_tokens": self._max_tokens, "thinking": {"type": "enabled"},
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
                # Print tool_calls messages and their following messages
                for i, m in enumerate(provider_msgs):
                    if m.get("tool_calls"):
                        next_msg = provider_msgs[i+1] if i+1 < len(provider_msgs) else {}
                        print(f"[DeepSeek] msg[{i}]: tool_calls ids={[tc['id'] for tc in m['tool_calls']]} next_role={next_msg.get('role')} next_tcid={next_msg.get('tool_call_id')}")
            resp.raise_for_status()
            return self._converter.from_provider(resp.json())
