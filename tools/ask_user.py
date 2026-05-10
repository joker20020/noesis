from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult


class AskUserTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="ask_user",
            description="Request human input when the agent cannot proceed autonomously.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        question = call.arguments["question"]
        options = call.arguments.get("options", [])
        output = f"[ASK_USER] {question}"
        if options:
            output += "\nOptions: " + ", ".join(options)
        return ToolResult(call_id=call.id, name="ask_user", success=True, output=output)
