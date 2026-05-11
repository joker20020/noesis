"""MCP (Model Context Protocol) client manager — connects to external MCP servers."""
from contextlib import AsyncExitStack
from typing import Any

from tools.base import ToolResult

# Optional import — graceful degradation if mcp is not installed
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


class McpClientManager:
    """Manages connections to multiple MCP servers via stdio or SSE."""

    def __init__(self, configs: list):
        self._configs = configs
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, dict] = {}  # tool_name -> {server_name, schema}

    async def initialize(self):
        if not HAS_MCP:
            raise RuntimeError("pip install mcp")
        for cfg in self._configs:
            await self._connect(cfg)
        if self._tools:
            print(f"[MCP] Connected {len(self._sessions)} servers, {len(self._tools)} tools available")
        else:
            print("[MCP] No servers configured or no tools found")

    async def _connect(self, cfg):
        name = cfg.name
        try:
            if cfg.transport == "sse" and cfg.url:
                read, write = await self._exit_stack.enter_async_context(sse_client(cfg.url))
            elif cfg.command:
                env = cfg.env or {}
                params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args or [],
                    env=env,
                )
                read, write = await self._exit_stack.enter_async_context(stdio_client(params))
            else:
                print(f"[MCP] Skip {name}: no command or url")
                return

            session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[name] = session

            tools_resp = await session.list_tools()
            for tool in tools_resp.tools:
                self._tools[tool.name] = {
                    "server": name,
                    "schema": tool,
                }
            print(f"[MCP] {name}: {len(tools_resp.tools)} tools")
        except Exception as e:
            print(f"[MCP] Failed to connect {name}: {e}")

    def get_schemas(self) -> list[dict]:
        schemas = []
        for info in self._tools.values():
            tool = info["schema"]
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema or {},
                }
            })
        return schemas

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        info = self._tools.get(name)
        if info is None:
            return ToolResult(
                call_id="", name=name, success=False,
                output="", error=f"MCP tool not found: {name}",
            )
        session = self._sessions[info["server"]]
        try:
            result = await session.call_tool(name, arguments=arguments)
            # Convert CallToolResult -> ToolResult
            texts = []
            is_error = result.isError if hasattr(result, "isError") else False
            for content in result.content:
                if hasattr(content, "text"):
                    texts.append(content.text)
                else:
                    texts.append(str(content))
            output = "\n".join(texts)
            return ToolResult(
                call_id="", name=name, success=not is_error,
                output=output, error=output if is_error else None,
            )
        except Exception as e:
            return ToolResult(
                call_id="", name=name, success=False,
                output="", error=str(e),
            )

    async def cleanup(self):
        await self._exit_stack.aclose()
        self._sessions.clear()
        self._tools.clear()
