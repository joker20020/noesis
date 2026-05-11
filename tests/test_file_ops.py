import pytest
from pathlib import Path
from tools.file_ops import FileReadTool, FileWriteTool, FilePatchTool, expand_file_refs
from tools.base import ToolCall


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


class TestFileReadTool:
    async def test_read_basic(self, temp_dir):
        tool = FileReadTool()
        path = temp_dir / "test.txt"
        path.write_text("line1\nline2\nline3\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_read", arguments={"path": str(path)})
        result = await tool.execute(call)
        assert result.success
        assert "line1" in result.output
        assert "line2" in result.output

    async def test_read_keyword_with_context(self, temp_dir):
        tool = FileReadTool()
        path = temp_dir / "test.txt"
        lines = [f"line {i:02d}" for i in range(1, 21)]
        lines[9] = "target keyword here"  # line 10
        path.write_text("\n".join(lines), encoding="utf-8")

        call = ToolCall(id="1", name="file_read", arguments={"path": str(path), "keyword": "target", "count": 10})
        result = await tool.execute(call)
        assert result.success
        assert "target keyword here" in result.output
        # Should include some context lines
        lines_in_output = result.output.count("|")
        assert lines_in_output > 1

    async def test_read_total_lines_hint(self, temp_dir):
        tool = FileReadTool()
        path = temp_dir / "test.txt"
        path.write_text("\n".join([f"line {i}" for i in range(1, 101)]), encoding="utf-8")

        call = ToolCall(id="1", name="file_read", arguments={"path": str(path), "count": 10})
        result = await tool.execute(call)
        assert result.success
        assert "100" in result.output
        assert "PARTIAL" in result.output

    async def test_read_not_found_suggestion(self, temp_dir):
        tool = FileReadTool()
        # Create a similar file first (need to read it to populate _read_dirs)
        similar = temp_dir / "actual_file.txt"
        similar.write_text("content", encoding="utf-8")

        # Read the similar file first to register its directory
        call1 = ToolCall(id="1", name="file_read", arguments={"path": str(similar)})
        await tool.execute(call1)

        # Now try a typo
        call2 = ToolCall(id="2", name="file_read", arguments={"path": str(temp_dir / "actul_file.txt")})
        result = await tool.execute(call2)
        assert not result.success
        assert "Did you mean" in result.output

    async def test_read_line_truncation(self, temp_dir):
        tool = FileReadTool()
        path = temp_dir / "test.txt"
        path.write_text("a" * 10000 + "\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_read", arguments={"path": str(path), "count": 1})
        result = await tool.execute(call)
        assert result.success
        assert "[TRUNCATED]" in result.output


class TestFileWriteTool:
    async def test_write_overwrite(self, temp_dir):
        tool = FileWriteTool()
        path = temp_dir / "test.txt"

        call = ToolCall(id="1", name="file_write", arguments={"path": str(path), "content": "hello"})
        result = await tool.execute(call)
        assert result.success
        assert path.read_text(encoding="utf-8") == "hello"

    async def test_write_append(self, temp_dir):
        tool = FileWriteTool()
        path = temp_dir / "test.txt"
        path.write_text("hello\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_write", arguments={"path": str(path), "content": "world\n", "mode": "append"})
        result = await tool.execute(call)
        assert result.success
        assert path.read_text(encoding="utf-8") == "hello\nworld\n"

    async def test_write_prepend(self, temp_dir):
        tool = FileWriteTool()
        path = temp_dir / "test.txt"
        path.write_text("world\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_write", arguments={"path": str(path), "content": "hello\n", "mode": "prepend"})
        result = await tool.execute(call)
        assert result.success
        assert path.read_text(encoding="utf-8") == "hello\nworld\n"

    async def test_write_extract_from_tags(self, temp_dir):
        tool = FileWriteTool()
        path = temp_dir / "test.txt"

        content = "before\n<file_content>\nactual content\n</file_content>\nafter"
        call = ToolCall(id="1", name="file_write", arguments={"path": str(path), "content": content})
        result = await tool.execute(call)
        assert result.success
        assert path.read_text(encoding="utf-8") == "actual content"

    async def test_write_with_file_refs(self, temp_dir):
        ref_file = temp_dir / "ref.txt"
        ref_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        tool = FileWriteTool()
        path = temp_dir / "test.txt"

        content = f"Before {{file:{ref_file}:2:3}} After"
        call = ToolCall(id="1", name="file_write", arguments={"path": str(path), "content": content})
        result = await tool.execute(call)
        assert result.success
        written = path.read_text(encoding="utf-8")
        assert "line2" in written
        assert "line3" in written


class TestFilePatchTool:
    async def test_patch_success(self, temp_dir):
        tool = FilePatchTool()
        path = temp_dir / "test.txt"
        path.write_text("hello world\nfoo bar\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_patch", arguments={
            "path": str(path),
            "old_content": "hello world",
            "new_content": "hi there"
        })
        result = await tool.execute(call)
        assert result.success
        assert path.read_text(encoding="utf-8") == "hi there\nfoo bar\n"

    async def test_patch_not_found_detailed_error(self, temp_dir):
        tool = FilePatchTool()
        path = temp_dir / "test.txt"
        path.write_text("hello world\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_patch", arguments={
            "path": str(path),
            "old_content": "nonexistent",
            "new_content": "replacement"
        })
        result = await tool.execute(call)
        assert not result.success
        assert "file_read" in result.error.lower() or "confirm" in result.error.lower()

    async def test_patch_multiple_matches(self, temp_dir):
        tool = FilePatchTool()
        path = temp_dir / "test.txt"
        path.write_text("abc\nabc\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_patch", arguments={
            "path": str(path),
            "old_content": "abc",
            "new_content": "xyz"
        })
        result = await tool.execute(call)
        assert not result.success
        assert "unique" in result.error.lower() or "2" in result.error

    async def test_patch_with_file_refs(self, temp_dir):
        ref_file = temp_dir / "ref.txt"
        ref_file.write_text("replacement text", encoding="utf-8")

        tool = FilePatchTool()
        path = temp_dir / "test.txt"
        path.write_text("hello world\n", encoding="utf-8")

        call = ToolCall(id="1", name="file_patch", arguments={
            "path": str(path),
            "old_content": "hello world",
            "new_content": f"{{file:{ref_file}:1:1}}"
        })
        result = await tool.execute(call)
        assert result.success
        assert path.read_text(encoding="utf-8") == "replacement text\n"


class TestExpandFileRefs:
    def test_basic_expansion(self, temp_dir):
        ref_file = temp_dir / "ref.txt"
        ref_file.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")

        text = f"Before {{file:{ref_file}:2:4}} After"
        result = expand_file_refs(text)
        assert "line2" in result
        assert "line3" in result
        assert "line4" in result
        assert "line1" not in result
        assert "line5" not in result

    def test_missing_file_raises(self, temp_dir):
        text = "Before {{file:/nonexistent/path.txt:1:3}} After"
        with pytest.raises(ValueError):
            expand_file_refs(text)

    def test_invalid_line_range_raises(self, temp_dir):
        ref_file = temp_dir / "ref.txt"
        ref_file.write_text("line1\n", encoding="utf-8")

        text = f"Before {{file:{ref_file}:1:5}} After"
        with pytest.raises(ValueError):
            expand_file_refs(text)
