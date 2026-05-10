"""Code execution tool — optimized per GenericAgent design."""
import asyncio
import subprocess
from pathlib import Path
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult

DISPLAY_MAX = 600
STORE_MAX = 10000


class CodeRunTool(BaseTool):
    def __init__(self, workspace_dir: str = "./workspace"):
        self._workspace = Path(workspace_dir).resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)

    def schema(self):
        return ToolSchema(
            name="code_run",
            description="Execute code or shell commands. Supports python, bash/sh/shell, powershell/ps1. One invocation per round. Output truncated to 600 chars for display, full output in stored result.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The code or command to execute"},
                    "code_type": {"type": "string", "description": "'python' (default) writes to .py file; 'bash'/'sh'/'shell' runs inline; 'powershell'/'ps1' runs inline"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)"},
                    "cwd": {"type": "string", "description": "Working directory (default workspace)"},
                },
                "required": ["command"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        command = call.arguments["command"]
        code_type = call.arguments.get("code_type", "python")
        timeout = call.arguments.get("timeout", 60)
        cwd = call.arguments.get("cwd") or str(self._workspace)

        if code_type in ("python", "py"):
            return await self._run_python(command, timeout, cwd)
        elif code_type in ("bash", "sh", "shell"):
            return await self._run_shell(command, timeout, cwd, "bash")
        elif code_type in ("powershell", "ps1", "pwsh"):
            return await self._run_shell(command, timeout, cwd, "powershell")
        else:
            return await self._run_shell(command, timeout, cwd, "bash")

    async def _run_python(self, code: str, timeout: int, cwd: str) -> ToolResult:
        script_path = Path(cwd).resolve() / f"_cr_{abs(hash(code)) % 100000:05d}.py"
        script_path.write_text(code, encoding="utf-8")
        try:
            return await self._exec(["python", str(script_path.resolve())], timeout, cwd)
        finally:
            try:
                script_path.unlink()
            except Exception:
                pass

    async def _run_shell(self, cmd: str, timeout: int, cwd: str, shell_type: str) -> ToolResult:
        if shell_type == "bash":
            return await self._exec(["bash", "-c", cmd], timeout, cwd)
        else:
            return await self._exec(["powershell", "-Command", cmd], timeout, cwd)

    async def _exec(self, args: list, timeout: int, cwd: str) -> ToolResult:
        def _run():
            return subprocess.run(args, capture_output=True, text=True,
                                  cwd=cwd, timeout=timeout, errors="replace")

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired:
            return ToolResult(call_id="", name="code_run", success=False,
                            output=f"(killed after {timeout}s)", error=f"Timeout after {timeout}s")

        out = (proc.stdout or "") + ("\n[stderr]\n" + proc.stderr if proc.stderr else "")
        if not out.strip():
            out = f"(exit code {proc.returncode}, no output)"

        return ToolResult(
            call_id="", name="code_run",
            success=proc.returncode == 0,
            output=out[:STORE_MAX],
            error=None if proc.returncode == 0 else f"Exit code: {proc.returncode}",
        )
