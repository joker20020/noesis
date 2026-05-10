"""Web interaction tools — optimized per GenericAgent design."""
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class WebScanTool(BaseTool):
    def __init__(self):
        self._browser = None
        self._context = None

    def schema(self):
        return ToolSchema(
            name="web_scan",
            description="Scan a web page. tabs_only=True lists open tabs (cheap). text_only=True strips HTML tags for cleaner output. switch_tab_id switches tabs before scanning.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to (creates new tab)"},
                    "tabs_only": {"type": "boolean", "description": "Return only tab list, no page content. Saves tokens."},
                    "text_only": {"type": "boolean", "description": "Strip HTML tags for cleaner text output"},
                    "switch_tab_id": {"type": "string", "description": "Tab ID to switch to before scanning"},
                },
                "required": [],
            },
        )

    async def _ensure_browser(self):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed")
        if self._browser is None:
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch()
            self._context = await self._browser.new_context()

    async def execute(self, call: ToolCall) -> ToolResult:
        await self._ensure_browser()
        tabs_only = call.arguments.get("tabs_only", False)
        text_only = call.arguments.get("text_only", False)
        switch_id = call.arguments.get("switch_tab_id")
        url = call.arguments.get("url")

        try:
            # Tab listing
            pages = self._context.pages
            tab_info = [{"id": f"tab_{i}", "url": p.url[:80], "title": await p.title()}
                       for i, p in enumerate(pages)]

            if tabs_only:
                return ToolResult(call_id=call.id, name="web_scan", success=True,
                                output=f"Tabs ({len(pages)}):\n" + "\n".join(
                                    f"  {t['id']}: {t['title'][:40]} | {t['url']}" for t in tab_info))

            # Tab switching
            page = pages[-1] if pages else None
            if switch_id:
                try:
                    idx = int(switch_id.replace("tab_", ""))
                    if 0 <= idx < len(pages):
                        page = pages[idx]
                        await page.bring_to_front()
                except (ValueError, IndexError):
                    pass

            # Navigate if URL provided
            if url:
                page = await self._context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if not page:
                return ToolResult(call_id=call.id, name="web_scan", success=False,
                                output="", error="No page available. Provide a URL or open a tab first.")

            # Extract content
            if text_only:
                text = await page.evaluate("document.body.innerText")
                output = text[:10000]
            else:
                html = await page.content()
                output = html[:35000]

            return ToolResult(call_id=call.id, name="web_scan", success=True, output=output)

        except Exception as e:
            return ToolResult(call_id=call.id, name="web_scan", success=False, output="", error=str(e))

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None


class WebExecuteJsTool(BaseTool):
    def __init__(self, browser_holder: WebScanTool):
        self._browser = browser_holder

    def schema(self):
        return ToolSchema(
            name="web_execute_js",
            description="Execute JavaScript in the current browser page. save_to_file writes full output to disk (cheap display). no_monitor skips change detection for faster execution.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "JavaScript code to execute"},
                    "switch_tab_id": {"type": "string", "description": "Tab ID to switch to before execution"},
                    "save_to_file": {"type": "boolean", "description": "Save full result to file (display shows preview only)"},
                    "no_monitor": {"type": "boolean", "description": "Skip page change monitoring for faster execution"},
                },
                "required": ["code"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        await self._browser._ensure_browser()
        code = call.arguments["code"]
        save_to_file = call.arguments.get("save_to_file", False)
        switch_id = call.arguments.get("switch_tab_id")

        try:
            pages = self._browser._context.pages
            page = pages[-1] if pages else None
            if switch_id:
                try:
                    idx = int(switch_id.replace("tab_", ""))
                    if 0 <= idx < len(pages):
                        page = pages[idx]
                        await page.bring_to_front()
                except (ValueError, IndexError):
                    pass

            if not page:
                return ToolResult(call_id=call.id, name="web_execute_js", success=False,
                                output="", error="No page available")

            result = await page.evaluate(code)
            result_str = str(result)
            display = result_str[:600]

            if save_to_file and len(result_str) > 600:
                from pathlib import Path
                f = Path("./workspace") / f"js_result_{abs(hash(code)) % 100000:05d}.txt"
                f.write_text(result_str, encoding="utf-8")
                display += f"\n(full output saved to {f})"

            return ToolResult(call_id=call.id, name="web_execute_js", success=True, output=display)

        except Exception as e:
            return ToolResult(call_id=call.id, name="web_execute_js", success=False, output="", error=str(e))
