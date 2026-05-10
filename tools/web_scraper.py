"""Lightweight web scraper using httpx — always works, no browser needed."""
import asyncio
import httpx
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult


class WebScraperTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="web_scraper",
            description="Fetch and parse web pages using HTTP requests. Returns page text content. Supports custom headers, timeout control. Use for API calls, static page scraping, and data extraction.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "method": {"type": "string", "description": "HTTP method: GET or POST (default GET)"},
                    "headers": {"type": "object", "description": "Custom HTTP headers"},
                    "body": {"type": "string", "description": "Request body for POST"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)"},
                },
                "required": ["url"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        url = call.arguments["url"]
        method = call.arguments.get("method", "GET").upper()
        headers = call.arguments.get("headers") or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        timeout = call.arguments.get("timeout", 15)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                if method == "POST":
                    resp = await client.post(url, headers=headers, content=call.arguments.get("body", ""))
                else:
                    resp = await client.get(url, headers=headers)

            status = resp.status_code
            content_type = resp.headers.get("content-type", "")
            text = resp.text[:15000]

            lines = [
                f"HTTP {status} | {content_type[:50]} | {len(resp.text)} bytes",
                f"URL: {url}",
                "",
                text,
            ]

            if len(resp.text) > 15000:
                lines.append(f"\n... ({len(resp.text) - 15000} more bytes)")

            return ToolResult(
                call_id=call.id, name="web_scraper",
                success=200 <= status < 400,
                output="\n".join(lines),
                error=None if 200 <= status < 400 else f"HTTP {status}",
            )
        except httpx.TimeoutException:
            return ToolResult(call_id=call.id, name="web_scraper", success=False,
                            output="", error=f"Timeout after {timeout}s")
        except Exception as e:
            return ToolResult(call_id=call.id, name="web_scraper", success=False,
                            output="", error=str(e))
