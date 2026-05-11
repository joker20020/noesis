"""LLM-powered SOP optimization and variant detection."""
import json
from pathlib import Path
from memory.neo4j_client import Neo4jClient
from llm.base import LlmClient, Message


OPTIMIZE_PROMPT = """Compare the SOP with actual execution traces. Detect semantic deviations.

Current SOP:
{sop_content}

Recent execution traces (tool calls with parameters):
{trace_with_params}

## Analysis Instructions
Analyze these dimensions internally, then synthesize your findings:
1. **Step presence**: Did execution follow all SOP steps? Were any skipped?
2. **Step order**: Was the sequence different, even if tool names match?
3. **Parameter drift**: Were tools called with different arguments than SOP specifies?
4. **New patterns**: Were tools used that aren't in the SOP? Is this a one-off or trend?
5. **Error handling**: Did execution encounter errors not covered in SOP?

Only suggest changes if evidence is strong (>= 2 occurrences or clear error pattern).

## Output Schema (strict — only these fields)
{{
  "suggestions": [
    "specific, actionable suggestion 1",
    "specific, actionable suggestion 2"
  ],
  "variant_detected": true or false,
  "variant_description": "if execution systematically diverged from SOP, describe the new pattern",
  "recommended_updates": "specific markdown text to insert into or modify in the SOP"
}}

Output ONLY valid JSON. No extra fields.
"""


class SopOptimizer:
    def __init__(self, neo4j: Neo4jClient, llm: LlmClient | None = None):
        self._neo4j = neo4j
        self._llm = llm

    async def optimize(self, skill_id: str, trace: str = "") -> dict | None:
        skill = await self._get_skill(skill_id)
        if not skill or skill.get("stage") not in ("SOP", "CODE"):
            return None

        sop_path = Path(skill["dir"]) / "SKILL.md"
        current_sop = sop_path.read_text(encoding="utf-8") if sop_path.exists() else ""

        if trace:
            # Parse tool names from passed trace
            tool_names = self._parse_tools_from_trace(trace)
        else:
            tool_names = await self._get_tool_sequence(skill_id)
        if len(tool_names) < 3:
            return None

        if self._llm:
            try:
                resp = await self._llm.chat([
                    Message.text_msg(role="user", text=OPTIMIZE_PROMPT.format(
                        sop_content=current_sop[:3000],
                        trace_with_params=" -> ".join(tool_names[-30:]),
                    ))
                ])
                contents = ''.join([c.text if c.type == "text" and c.text else "" for c in resp.content])
                data = json.loads(contents or "{}")
            except Exception:
                data = {}
        else:
            data = self._heuristic_analyze(current_sop, tool_names)

        return {
            "skill_id": skill_id, "execution_count": len(tool_names),
            "suggestions": data.get("suggestions", []),
            "variant_detected": data.get("variant_detected", False),
            "variant_description": data.get("variant_description", ""),
            "recommended_updates": data.get("recommended_updates", ""),
        }

    def _parse_tools_from_trace(self, trace: str) -> list[str]:
        """Extract tool names from a trace string."""
        tools = []
        for line in trace.split("\n"):
            if line.startswith("[tool:"):
                name = line.split("]")[0].replace("[tool:", "")
                tools.append(name)
        return tools

    def _heuristic_analyze(self, sop: str, tools: list[str]) -> dict:
        suggestions = []
        for tool in list(dict.fromkeys(tools))[-5:]:
            if tool not in sop:
                suggestions.append(f"Add step for '{tool}' — frequently used, missing from SOP")
        return {"suggestions": suggestions, "variant_detected": False,
                "variant_description": "", "recommended_updates": ""}

    async def _get_tool_sequence(self, skill_id: str) -> list[str]:
        traces = await self._neo4j.run(
            """MATCH (s:Session)-[:USED_SKILL]->(sk:Skill {skill_id: $sid})
               MATCH (s)-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               WHERE step.role = 'system'
               RETURN step.content AS content ORDER BY s.created_at DESC LIMIT 40""",
            {"sid": skill_id},
        )
        tools = []
        for t in traces:
            content = t.get("content", "")
            if isinstance(content, str):
                try:
                    for block in json.loads(content):
                        if block.get("type") == "tool_result":
                            tools.append(block.get("name", ""))
                except Exception:
                    pass
        return tools

    async def optimize_all(self, min_usage: int = 3) -> list[dict]:
        skills = await self._neo4j.run(
            """MATCH (s:Skill) WHERE s.stage IN ['SOP', 'CODE']
               AND coalesce(s.usage_count, 0) >= $min RETURN s.skill_id AS id""",
            {"min": min_usage},
        )
        results = []
        for r in skills:
            result = await self.optimize(r["id"])
            if result:
                results.append(result)
        return results

    async def _get_skill(self, skill_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) RETURN s", {"sid": skill_id},
        )
        return dict(records[0]["s"]) if records else None
