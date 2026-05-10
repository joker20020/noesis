import json
import httpx
from llm.base import LlmClient, LlmResponse, Message, ToolCall, ToolSchema
from agent.config import LLMConfig


class DeepSeekClient(LlmClient):
    def __init__(self, config: LLMConfig):
        self.model = config.model
        self.base_url = config.base_url or "https://api.deepseek.com"
        self._api_key = config.api_key
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature

    async def chat(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> LlmResponse:
        msgs = []
        for m in messages:
            if m.role == "tool":
                # Send tool results as plain user-context messages to avoid
                # API requirement for preceding tool_calls in history
                msgs.append({"role": "user", "content": f"[Tool result: {m.name or 'tool'}] {m.content}"})
            else:
                msgs.append({"role": m.role, "content": m.content})
        # Ensure messages alternate: merge consecutive same-role messages
        merged = []
        for m in msgs:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(m)
        msgs = merged
        body: dict = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            # tools are already in API format from dispatcher.get_schemas()
            body["tools"] = tools if isinstance(tools[0], dict) else [{
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            } for t in tools]

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code >= 400:
                print(f"[DeepSeek {resp.status_code}] Request model={body['model']} msgs={len(body['messages'])} tools={len(body.get('tools', []))}")
                print(f"[DeepSeek {resp.status_code}] Response: {resp.text[:1000]}")
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        tool_calls = []
        if choice["message"].get("tool_calls"):
            for tc in choice["message"]["tool_calls"]:
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                ))
        return LlmResponse(
            content=choice["message"].get("content"),
            tool_calls=tool_calls,
        )