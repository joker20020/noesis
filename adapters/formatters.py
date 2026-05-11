"""Event formatters for platform adapters — convert agent events to platform-friendly text."""
import json


def format_event(event: dict, platform: str = "generic") -> str | None:
    """Format an agent event for a specific platform. Returns None to skip."""
    etype = event.get("type")

    if etype == "thinking":
        content = _truncate(event.get("content", ""), 800)
        return f"🤔 {content}"

    elif etype == "text":
        return event.get("content", "")

    elif etype == "tool_use":
        name = event.get("name", "tool")
        args = event.get("arguments", {})
        args_str = json.dumps(args, ensure_ascii=False)[:300]
        return f"🔧 {name}({args_str})"

    elif etype == "tool_result":
        name = event.get("name", "tool")
        content = _truncate(event.get("content", ""), 1000)
        return f"📤 {name}: {content}"

    elif etype == "status":
        return f"⏳ {event.get('status', '')}"

    elif etype == "done":
        return event.get("content", "")

    elif etype == "message":
        # Legacy fallback
        return event.get("content", "")

    return None


def should_skip_for_platform(event: dict, platform: str) -> bool:
    """Determine if an event should be skipped for a rate-limited platform."""
    if platform not in ("wechat", "qq"):
        return False

    etype = event.get("type")
    # For rate-limited platforms, skip empty thinking and very short status
    if etype == "thinking" and len(event.get("content", "")) < 20:
        return True
    if etype == "status":
        return True
    return False


def merge_events(events: list[dict], platform: str) -> list[str]:
    """Merge consecutive short events into fewer messages (for rate-limited platforms)."""
    if platform not in ("wechat", "qq"):
        return [format_event(e, platform) for e in events if format_event(e, platform)]

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
        if e.get("type") in ("tool_use", "tool_result"):
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
