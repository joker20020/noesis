import json
from openai import AsyncOpenAI
from llm.base import LlmClient, LlmResponse, Message, ToolCall, ToolSchema
from agent.config import LLMConfig


class OpenAIClient(LlmClient):
    def __init__(self, config: LLMConfig):
        self.model = config.model
        client_kwargs = {"api_key": config.api_key}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**client_kwargs)
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature

    async def chat(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> LlmResponse:
        msgs = []
        for m in messages:
            if m.role == "tool":
                msgs.append({"role": "user", "content": f"[Tool result: {m.name or 'tool'}] {m.content}"})
            else:
                msgs.append({"role": m.role, "content": m.content})
        merged = []
        for m in msgs:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(m)
        msgs = merged
        kwargs: dict = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            # tools are already in API format from dispatcher.get_schemas()
            kwargs["tools"] = tools if isinstance(tools[0], dict) else [{
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            } for t in tools]

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))
        return LlmResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
        )
