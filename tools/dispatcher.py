from tools.base import BaseTool, ToolCall, ToolResult


class ToolDispatcher:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._mcp = None

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def set_mcp(self, mcp):
        self._mcp = mcp

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
        if self._mcp is not None:
            try:
                schemas.extend(self._mcp.get_schemas())
            except Exception:
                pass
        return schemas

    async def dispatch(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is not None:
            try:
                return await tool.execute(call)
            except Exception as e:
                return ToolResult(
                    call_id=call.id, name=call.name, success=False,
                    output="", error=str(e),
                )
        if self._mcp is not None:
            try:
                return await self._mcp.call_tool(call.name, call.arguments)
            except Exception as e:
                return ToolResult(
                    call_id=call.id, name=call.name, success=False,
                    output="", error=str(e),
                )
        return ToolResult(
            call_id=call.id, name=call.name, success=False,
            output="", error=f"Unknown tool: {call.name}",
        )

    def tool_names(self) -> list[str]:
        names = list(self._tools.keys())
        if self._mcp is not None:
            try:
                names.extend(self._mcp._tools.keys())
            except Exception:
                pass
        return names
