def truncate_head_tail(text: str, max_len: int = 10000) -> str:
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n... [{len(text) - max_len} chars truncated] ...\n" + text[-half:]


class CompressionPipeline:
    def __init__(self, context_budget_chars: int = 90000):
        self.budget = context_budget_chars

    def stage1_tool_output(self, tool_name: str, output: str) -> str:
        thresholds = {
            "code_run": 10000,
            "web_execute_js": 8000,
            "web_scan": 10000,
            "file_read": 20000,
            "memory_search": 0,
        }
        limit = thresholds.get(tool_name, 10000)
        if limit == 0 or len(output) <= limit:
            return output
        return truncate_head_tail(output, max_len=limit)

    def stage2_compress_tags(self, messages: list[dict], recent_exempt: int = 10) -> list[dict]:
        result = []
        for i, msg in enumerate(messages):
            is_recent = i >= len(messages) - recent_exempt
            if is_recent:
                result.append(msg)
                continue
            content = msg.get("content", "")
            if len(content) > 800:
                result.append({**msg, "content": truncate_head_tail(content, max_len=800)})
            else:
                result.append(msg)
        return result

    def stage3_evict(self, messages: list[dict]) -> list[dict]:
        target = int(self.budget * 0.6)
        while self._char_count(messages) > target and len(messages) > 9:
            messages = messages[1:]
        while messages and messages[0].get("role") != "user":
            messages = messages[1:]
        return messages

    def _char_count(self, messages: list[dict]) -> int:
        import json
        return sum(len(json.dumps(m)) for m in messages)
