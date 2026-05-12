"""Event formatters for platform adapters — convert agent message events to platform-friendly text."""
import json


def format_event(event: dict, platform: str = "generic") -> str | None:
    """Format a message event by iterating over its content blocks. Returns None to skip."""
    if event.get("type") != "message":
        return None

    content = event.get("content", [])
    if not content:
        return None

    # If thinking coexists with text, label text so they don't blur together.
    has_thinking = any(b.get("type") == "thinking" and b.get("thinking") for b in content)

    parts = []
    for block in content:
        btype = block.get("type")
        if btype == "thinking":
            t = block.get("thinking", "")
            if t:
                parts.append(f"💭 思考过程\n{_truncate(t, 1000)}")
        elif btype == "text":
            t = block.get("text", "")
            if t:
                if has_thinking:
                    parts.append(f"📝 回复\n{t}")
                else:
                    parts.append(t)
        elif btype == "tool_use":
            name = block.get("name", "tool")
            inp = block.get("input", {})
            args_str = json.dumps(inp, ensure_ascii=False)[:300]
            parts.append(f"🔧 调用工具: {name}\n参数: {args_str}")
        elif btype == "tool_result":
            name = block.get("name", "tool")
            out = _truncate(block.get("output", ""), 1000)
            parts.append(f"📤 工具结果: {name}\n{out}")

    if not parts:
        return None
    return "\n\n".join(parts)


def should_skip_for_platform(event: dict, platform: str) -> bool:
    """Determine if a message event should be skipped for a rate-limited platform."""
    if platform not in ("wechat", "qq"):
        return False

    if event.get("type") != "message":
        return True

    content = event.get("content", [])
    has_meaningful = False
    for block in content:
        btype = block.get("type")
        if btype == "thinking" and len(block.get("thinking", "")) >= 2:
            has_meaningful = True
        elif btype in ("text", "tool_use", "tool_result"):
            has_meaningful = True
    return not has_meaningful


def merge_events(events: list[dict], platform: str) -> list[str]:
    """Merge consecutive short events into fewer messages (for rate-limited platforms).

    Deprecated: adapters now stream in real-time. Kept for backward compatibility.
    """
    merged: list[str] = []
    buffer: list[str] = []
    buf_len = 0
    MAX_BUF = 1800

    for e in events:
        if should_skip_for_platform(e, platform):
            continue
        text = format_event(e, platform)
        if not text:
            continue

        # tool_use and tool_result are important — flush buffer before them
        if any(block.get("type") in ("tool_use", "tool_result") for block in e.get("content", [])):
            if buffer:
                merged.append("\n".join(buffer))
                buffer = []
                buf_len = 0
            merged.append(text)
            continue

        if buf_len + len(text) + 1 > MAX_BUF:
            if buffer:
                merged.append("\n".join(buffer))
            buffer = [text]
            buf_len = len(text)
        else:
            buffer.append(text)
            buf_len += len(text) + 1

    if buffer:
        merged.append("\n".join(buffer))

    return merged


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 10] + "...[截断]"
