from tools.base import BaseTool, ToolCall, ToolResult


class ToolDispatcher:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict]:
        schemas = []
        for tool in self._tools.values():
            s = tool.schema()
            schemas.append({
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.parameters,
                }
            })
        return schemas

    async def dispatch(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.id, name=call.name, success=False,
                output="", error=f"Unknown tool: {call.name}",
            )
        try:
            return await tool.execute(call)
        except Exception as e:
            return ToolResult(
                call_id=call.id, name=call.name, success=False,
                output="", error=str(e),
            )

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
