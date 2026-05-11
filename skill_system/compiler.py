"""LLM-powered SOP→Code compiler with auto-validation."""
import subprocess
from pathlib import Path
from memory.neo4j_client import Neo4jClient
from llm.base import LlmClient, Message


COMPILE_PROMPT = """Generate executable Python code from this SOP. Output TWO files separated by `===TEST===`.

SOP:
{sop_content}

## Code Requirements (apply to main.py)
1. **Argument validation**: Use argparse with type checking; reject invalid inputs.
2. **Error handling**: Wrap external calls in try/except; log errors with context.
3. **Timeout**: All subprocess calls must have timeout (default 30s).
4. **Progress logging**: Print step name before execution; print completion status.
5. **Idempotency**: Where possible, check if step already done before repeating.
6. **Return codes**: Exit 0 on success, 1 on failure, 2 on partial success.

## Test Requirements (apply to test_main.py)
1. **Happy path**: Verify main.py runs with valid arguments.
2. **Error path**: Verify graceful failure with invalid arguments/missing files.
3. **Boundary**: Verify behavior at edge cases (empty input, max length, special chars).
4. **Mock external calls**: Use unittest.mock for network/subprocess to avoid side effects.

## Output Format
```python
# scripts/main.py
...
```

===TEST===

```python
# scripts/test_main.py
...
```

Output ONLY the two code blocks, no other text.
"""


class SopCompiler:
    def __init__(self, neo4j: Neo4jClient, llm: LlmClient, skills_dir: str = "./skills"):
        self._neo4j = neo4j
        self._llm = llm
        self._skills_dir = Path(skills_dir)

    async def compile_if_ready(self, skill_id: str) -> dict | None:
        skill = await self._get_skill(skill_id)
        if not skill:
            return None

        stage = skill.get("stage", "NL")
        confidence = float(skill.get("confidence", 0))
        usage = int(skill.get("usage_count", 0))

        if stage != "SOP":
            return {"status": "skipped", "reason": f"Stage is {stage}, must be SOP"}
        if confidence < 0.8:
            return {"status": "skipped", "reason": f"Confidence {confidence} < 0.8"}
        if usage < 5:
            return {"status": "skipped", "reason": f"Usage {usage} < 5"}

        sop_path = Path(skill["dir"]) / "SKILL.md"
        if not sop_path.exists():
            return {"status": "skipped", "reason": "SKILL.md not found"}

        sop_content = sop_path.read_text(encoding="utf-8")

        # Generate code via LLM
        try:
            resp = await self._llm.chat([
                Message.text_msg(role="user", text=COMPILE_PROMPT.format(sop_content=sop_content[:4000]))
            ])
            code = ''.join([c.text if c.type == "text" and c.text else "" for c in resp.content])
        except Exception as e:
            return {"status": "skipped", "reason": f"LLM error: {e}"}

        parts = code.split("===TEST===")
        main_code = parts[0].strip() if parts else ""
        test_code = parts[1].strip() if len(parts) > 1 else ""

        # Extract code blocks
        main_code = self._extract_code(main_code)
        test_code = self._extract_code(test_code)

        if not main_code:
            return {"status": "skipped", "reason": "No code generated"}

        scripts_dir = Path(skill["dir"]) / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "main.py").write_text(main_code, encoding="utf-8")
        (scripts_dir / "test_main.py").write_text(test_code or "# auto-generated test", encoding="utf-8")

        # Validate
        try:
            result = subprocess.run(
                ["python", str(scripts_dir / "test_main.py")] if test_code else ["python", str(scripts_dir / "main.py")],
                capture_output=True, text=True, cwd=str(scripts_dir), timeout=30,
            )
            passed = result.returncode == 0
        except Exception as e:
            passed = False
            result = type("R", (), {"returncode": -1, "stdout": "", "stderr": str(e)})()

        if passed:
            await self._neo4j.run(
                """MATCH (s:Skill {skill_id: $sid})
                   SET s.stage = 'CODE', s.version = coalesce(s.version, 1) + 1,
                       s.confidence = 0.95, s.updated_at = datetime()""",
                {"sid": skill_id},
            )
            sop_content = sop_content.replace('stage: "SOP"', 'stage: "CODE"')
            sop_path.write_text(sop_content, encoding="utf-8")
            return {"status": "compiled", "output": result.stdout[:500]}
        else:
            return {"status": "failed_validation", "output": f"{result.stdout}\n{result.stderr}"[:500]}

    def _extract_code(self, text: str) -> str:
        if "```python" in text:
            start = text.find("```python") + 9
            end = text.find("```", start)
            return text[start:end].strip() if end > start else text.strip()
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip() if end > start else text.strip()
        return text.strip()

    async def _get_skill(self, skill_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) RETURN s", {"sid": skill_id},
        )
        return dict(records[0]["s"]) if records else None
