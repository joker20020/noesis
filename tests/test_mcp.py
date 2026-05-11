"""Simple tests for MCP client manager.

These tests verify that McpClientManager can connect to stdio and SSE servers
and successfully call tools.

Prerequisites:
    - uv run python tests/mcp_stdio_server.py   (run in one terminal)
    - uv run python tests/mcp_sse_server.py     (run in another terminal)

Or use the helper fixtures below which spawn servers automatically.
"""

import asyncio
import pytest

from tools.mcp_client import McpClientManager
from agent.config import McpServerConfig


@pytest.mark.asyncio
async def test_stdio_server():
    """Test connection to the stdio MCP test server."""
    manager = McpClientManager([
        McpServerConfig(
            name="test-stdio",
            transport="stdio",
            command="uv",
            args=["run", "python", "tests/mcp_stdio_server.py"],
        )
    ])
    await manager.initialize()

    schemas = manager.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "add" in names
    assert "multiply" in names
    assert "greet" in names

    result = await manager.call_tool("add", {"a": 3, "b": 5})
    assert result.success is True
    assert "8" in result.output

    result = await manager.call_tool("greet", {"name": "Noesis"})
    assert result.success is True
    assert "Hello, Noesis!" in result.output

    await manager.cleanup()


@pytest.mark.asyncio
async def test_sse_server():
    """Test connection to the SSE MCP test server."""
    manager = McpClientManager([
        McpServerConfig(
            name="test-sse",
            transport="sse",
            url="http://127.0.0.1:8080/sse",
        )
    ])
    await manager.initialize()

    schemas = manager.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "get_time" in names
    assert "reverse" in names
    assert "count_chars" in names

    result = await manager.call_tool("reverse", {"text": "hello"})
    assert result.success is True
    assert "olleh" in result.output

    result = await manager.call_tool("count_chars", {"text": "noesis"})
    assert result.success is True
    assert "6" in result.output

    await manager.cleanup()
