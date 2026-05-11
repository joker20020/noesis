import difflib
import itertools
import os
import re
from collections import deque
from pathlib import Path

from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult


_read_dirs: set[str] = set()


def _scan_files(base: str, depth: int = 2):
    """Yield (name, path) for files under base, recursing up to depth levels."""
    try:
        for entry in os.scandir(base):
            if entry.is_file():
                yield (entry.name, entry.path)
            elif depth > 0 and entry.is_dir(follow_symlinks=False):
                yield from _scan_files(entry.path, depth - 1)
    except (PermissionError, OSError):
        pass


def expand_file_refs(text: str, base_dir: str | None = None) -> str:
    """Expand {{file:path:start:end}} references in text to actual file content."""
    pattern = r'\{file:(.+?):(\d+):(\d+)\}'

    def replacer(match):
        path_str, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        path = os.path.abspath(os.path.join(base_dir or '.', path_str))
        if not os.path.isfile(path):
            raise ValueError(f"Referenced file does not exist: {path}")
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        if start < 1 or end > len(lines) or start > end:
            raise ValueError(
                f"Line range out of bounds: {path} has {len(lines)} lines, requested {start}-{end}"
            )
        return ''.join(lines[start - 1:end])

    return re.sub(pattern, replacer, text)


def _extract_file_content(text: str) -> str | None:
    """Extract content from <file_content>...</file_content> tags or code blocks."""
    tags = re.findall(r"<file_content[^>]*>(.*?)</file_content>", text, re.DOTALL)
    if tags:
        return tags[-1].strip()
    blocks = re.findall(r"```[^\n]*\n([\s\S]*?)```", text)
    if blocks:
        return blocks[-1].strip()
    return None


class FileReadTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_read",
            description="Read file content with optional line range and keyword anchoring. "
                        "When using keyword, surrounding context lines are included. "
                        "For large files, a partial indicator shows total line count.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start": {"type": "integer", "description": "1-based start line (default: 1)"},
                    "count": {"type": "integer", "description": "Number of lines to read (default: 200)"},
                    "keyword": {"type": "string", "description": "Search keyword (case-insensitive). Returns context around first match."},
                    "show_linenos": {"type": "boolean", "description": "Show line numbers (default: true)"},
                },
                "required": ["path"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        if not path.exists():
            return self._handle_not_found(path)

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                stream = ((i, l.rstrip('\r\n')) for i, l in enumerate(f, 1))

                start = call.arguments.get("start", 1)
                count = call.arguments.get("count", 200)
                keyword = call.arguments.get("keyword")
                show_linenos = call.arguments.get("show_linenos", True)

                # Drop lines before start
                stream = itertools.dropwhile(lambda x: x[0] < start, stream)

                if keyword:
                    before = deque(maxlen=count // 3)
                    res = None
                    for i, line in stream:
                        if keyword.lower() in line.lower():
                            res = list(before) + [(i, line)] + list(itertools.islice(stream, count - len(before) - 1))
                            break
                        before.append((i, line))
                    if res is None:
                        fallback_msg = (
                            f"Keyword '{keyword}' not found after line {start}. "
                            f"Falling back to content from line {start}.\n\n"
                        )
                        stream = ((i, l.rstrip('\r\n')) for i, l in enumerate(open(path, 'r', encoding='utf-8', errors='replace'), 1))
                        stream = itertools.dropwhile(lambda x: x[0] < start, stream)
                        res = list(itertools.islice(stream, count))
                        return ToolResult(
                            call_id=call.id, name="file_read", success=False,
                            output=fallback_msg + self._format_lines(res, show_linenos, path),
                            error=f"Keyword '{keyword}' not found after line {start}"
                        )
                else:
                    res = list(itertools.islice(stream, count))

                output = self._format_lines(res, show_linenos, path)
                _read_dirs.add(str(path.parent.resolve()))
                return ToolResult(call_id=call.id, name="file_read", success=True, output=output)
        except Exception as e:
            return ToolResult(call_id=call.id, name="file_read", success=False, output="", error=str(e))

    def _format_lines(self, res: list[tuple[int, str]], show_linenos: bool, path: Path) -> str:
        realcnt = len(res)
        if realcnt == 0:
            return "(empty file or range beyond end)"

        # Dynamic per-line length limit
        L_MAX = min(max(100, 256000 // max(realcnt, 1)), 8000)
        TAG = " ... [TRUNCATED]"

        # Peek ahead to estimate total lines
        remaining = 0
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                total_in_file = sum(1 for _ in f)
            remaining = max(0, total_in_file - (res[0][0] - 1) - realcnt)
            total_lines = (res[0][0] - 1) + realcnt + remaining
        except Exception:
            total_lines = realcnt
            remaining = 0

        partial = total_lines > realcnt
        total_tag = f"[FILE] {total_lines} lines"
        if partial:
            total_tag += f" | PARTIAL showing {realcnt}; assess need for more"
        total_tag += "\n"

        # Truncate overly long lines
        formatted = [(i, line if len(line) <= L_MAX else line[:L_MAX] + TAG) for i, line in res]

        if show_linenos:
            result = "\n".join(f"{i}|{line}" for i, line in formatted)
            return total_tag + result
        else:
            result = "\n".join(line for _, line in formatted)
            if partial:
                result += f"\n\n[FILE PARTIAL: showing {realcnt}/{total_lines} lines; assess need for more]"
            return result

    def _handle_not_found(self, path: Path) -> ToolResult:
        msg = f"Error: File not found: {path}"
        try:
            target = path.name
            scan_dir = path.parent
            roots = [str(scan_dir.resolve())]
            # Also search in previously read directories
            roots.extend(d for d in _read_dirs if not d.startswith(str(scan_dir.resolve())))

            candidates = list(itertools.islice(
                (c for base in roots for c in _scan_files(base)), 2000
            ))
            top = sorted(
                [(difflib.SequenceMatcher(None, target.lower(), c[0].lower()).ratio(), c)
                 for c in candidates],
                key=lambda x: -x[0]
            )[:5]
            top = [(s, c) for s, c in top if s > 0.3]
            if top:
                msg += "\n\nDid you mean:\n" + "\n".join(
                    f"  {c[1]}  ({s:.0%})" for s, c in top
                )
        except Exception:
            pass
        return ToolResult(call_id="", name="file_read", success=False, output=msg, error=msg)


class FileWriteTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_write",
            description="Write content to a file. Supports overwrite (default), append, and prepend modes. "
                        "Content can include <file_content>...</file_content> tags which will be extracted automatically.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "description": "File content, or text containing <file_content>...</file_content> tags"},
                    "mode": {"type": "string", "enum": ["overwrite", "append", "prepend"], "description": "Write mode (default: overwrite)"},
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        mode = call.arguments.get("mode", "overwrite")
        raw_content = call.arguments["content"]

        # Try to extract from <file_content> tags or code blocks
        extracted = _extract_file_content(raw_content)
        if extracted is not None:
            content = extracted
        else:
            content = raw_content

        # Expand file references like {{file:path:start:end}}
        try:
            content = expand_file_refs(content, base_dir=str(path.parent))
        except ValueError as e:
            return ToolResult(
                call_id=call.id, name="file_write", success=False,
                output="", error=f"File reference expansion failed: {e}"
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if mode == "prepend":
                old = path.read_text(encoding="utf-8") if path.exists() else ""
                path.write_text(content + old, encoding="utf-8")
            elif mode == "append":
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
            else:
                path.write_text(content, encoding="utf-8")

            action = {"prepend": "Prepended to", "append": "Appended to"}.get(mode, "Written to")
            return ToolResult(call_id=call.id, name="file_write", success=True, output=f"{action} {path} ({len(content)} bytes)")
        except Exception as e:
            return ToolResult(call_id=call.id, name="file_write", success=False, output="", error=str(e))


class FilePatchTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_patch",
            description="Replace old_content with new_content. old_content must match exactly one location. "
                        "For reliable patching, use file_read first to confirm current content, then patch in small chunks.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_content": {"type": "string", "description": "Exact content to find and replace. Should be specific enough to match uniquely."},
                    "new_content": {"type": "string", "description": "Replacement content. Supports {{file:path:start:end}} references."},
                },
                "required": ["path", "old_content", "new_content"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        if not path.exists():
            return ToolResult(
                call_id=call.id, name="file_patch", success=False,
                output="", error=f"File not found: {path}"
            )

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                full_text = f.read()
        except Exception as e:
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error=str(e))

        old = call.arguments["old_content"]
        new_content = call.arguments["new_content"]

        if not old:
            return ToolResult(
                call_id=call.id, name="file_patch", success=False,
                output="", error="old_content is empty. Please provide the exact text to replace."
            )

        # Expand file references in new_content
        try:
            new_content = expand_file_refs(new_content, base_dir=str(path.parent))
        except ValueError as e:
            return ToolResult(
                call_id=call.id, name="file_patch", success=False,
                output="", error=f"File reference expansion failed: {e}"
            )

        count = full_text.count(old)
        if count == 0:
            error_msg = (
                "old_content not found in file. Suggestions:\n"
                "1. Use file_read first to confirm the exact current content.\n"
                "2. Try a smaller, more specific text chunk that includes surrounding context lines.\n"
                "3. If multiple patches are needed, apply them one at a time.\n"
                "4. Do NOT use file_write (overwrite) as a fallback — it destroys the original file."
            )
            return ToolResult(
                call_id=call.id, name="file_patch", success=False,
                output="", error=error_msg
            )
        if count > 1:
            error_msg = (
                f"old_content matches {count} locations, cannot determine unique position.\n"
                "Suggestions:\n"
                "1. Include more surrounding context lines in old_content to make it unique.\n"
                "2. Split the change into smaller, more specific patches.\n"
                "3. Use file_read to locate the exact occurrence you want to modify."
            )
            return ToolResult(
                call_id=call.id, name="file_patch", success=False,
                output="", error=error_msg
            )

        try:
            updated = full_text.replace(old, new_content, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            return ToolResult(
                call_id=call.id, name="file_patch", success=True,
                output="Patch applied successfully"
            )
        except Exception as e:
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error=str(e))
