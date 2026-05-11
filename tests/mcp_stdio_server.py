"""MCP stdio test server — simple calculator tools.

Run with: uv run python tests/mcp_stdio_server.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-stdio-server")


@mcp.tool()
def add(a: float, b: float) -> str:
    """Add two numbers."""
    return str(a + b)


@mcp.tool()
def multiply(a: float, b: float) -> str:
    """Multiply two numbers."""
    return str(a * b)


@mcp.tool()
def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}! Welcome from stdio MCP server."


if __name__ == "__main__":
    mcp.run(transport="stdio")
