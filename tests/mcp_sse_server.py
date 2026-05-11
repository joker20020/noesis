"""MCP SSE test server — simple text utilities over HTTP.

Run with: uv run python tests/mcp_sse_server.py
Then connect to http://localhost:8080/sse
"""
import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-sse-server")


@mcp.tool()
def get_time() -> str:
    """Return the current server time."""
    return datetime.datetime.now().isoformat()


@mcp.tool()
def reverse(text: str) -> str:
    """Reverse the input text."""
    return text[::-1]


@mcp.tool()
def count_chars(text: str) -> str:
    """Count characters in the input text."""
    return str(len(text))


if __name__ == "__main__":
    # FastMCP SSE uses settings.port (default 8000) and settings.host (default 127.0.0.1)
    # Override via environment: MCP_PORT=9000 uv run python tests/mcp_sse_server.py
    import os

    # custom_port = os.getenv("MCP_PORT")
    custom_port = 8050
    if custom_port:
        mcp.settings.port = int(custom_port)
    print(f"[MCP SSE] Starting on http://{mcp.settings.host}:{mcp.settings.port}/sse")
    mcp.run(transport="sse")
