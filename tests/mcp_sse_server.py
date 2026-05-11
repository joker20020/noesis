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
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"[MCP SSE] Starting on http://localhost:{port}/sse")
    mcp.run(transport="sse", port=port, host="127.0.0.1")
