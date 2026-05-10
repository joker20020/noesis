from pathlib import Path
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult


class FileReadTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_read",
            description="Read file content with optional line range and keyword anchoring",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start": {"type": "integer"},
                    "count": {"type": "integer"},
                    "keyword": {"type": "string"},
                },
                "required": ["path"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        if not path.exists():
            return ToolResult(call_id=call.id, name="file_read", success=False, output="", error=f"File not found: {path}")
        lines = path.read_text(encoding="utf-8").splitlines()
        start = call.arguments.get("start", 1) - 1
        keyword = call.arguments.get("keyword")
        if keyword:
            for i, line in enumerate(lines):
                if keyword in line:
                    start = i
                    break
        count = call.arguments.get("count", len(lines) - start)
        selected = lines[start:start + count]
        output = "\n".join(f"{start + i + 1}\t{line}" for i, line in enumerate(selected))
        return ToolResult(call_id=call.id, name="file_read", success=True, output=output)


class FileWriteTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_write",
            description="Write full content to a file, creating or overwriting",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(call.arguments["content"], encoding="utf-8")
        return ToolResult(call_id=call.id, name="file_write", success=True, output=f"Written to {path}")


class FilePatchTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_patch",
            description="Replace old_content with new_content. old_content must match exactly one location.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_content": {"type": "string", "description": "Exact content to find and replace"},
                    "new_content": {"type": "string", "description": "Replacement content"},
                },
                "required": ["path", "old_content", "new_content"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        if not path.exists():
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error=f"File not found: {path}")
        content = path.read_text(encoding="utf-8")
        old = call.arguments["old_content"]
        count = content.count(old)
        if count == 0:
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error="old_content not found in file")
        if count > 1:
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error=f"old_content matches {count} locations, must be unique")
        path.write_text(content.replace(old, call.arguments["new_content"], 1), encoding="utf-8")
        return ToolResult(call_id=call.id, name="file_patch", success=True, output="Patch applied successfully")
