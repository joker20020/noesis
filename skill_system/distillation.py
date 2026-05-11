"""Gradual evolution engine — one request at a time, with execution trace context."""
import json
from pathlib import Path
from memory.neo4j_client import Neo4jClient
from skill_system.registry import SkillRegistry
from llm.base import LlmClient, Message


SOP_PROMPT = """Generate an SOP from this skill's execution history.

Skill: {skill_name} ({skill_id})
Current stage: {stage}

Recent execution steps:
{trace}

Summary from user: {summary}

## SOP Quality Standards (follow these, but do not output scores)
Your output must be a markdown document that is:
1. **Executable**: Every step maps to a specific tool call or action found in the trace.
2. **Bounded**: Lists prerequisites, expected inputs, and success criteria.
3. **Resilient**: Includes "Common Mistakes" and error recovery steps observed in the trace.
4. **Verifiable**: Each step has an observable output or check.

## Required Sections
- ## Overview: One sentence on what this SOP achieves.
- ## When to Use: Specific trigger conditions.
- ## Prerequisites: Required tools, credentials, or state.
- ## Core Pattern: Numbered steps, each step must reference a tool/action from the trace.
- ## Common Mistakes: Observed errors and their fixes.
- ## Variants (optional): If the trace shows conditional branches, document them.

## Output Format Rules
- Output ONLY the SKILL.md markdown content.
- Do NOT include any JSON, scores, or evaluation blocks.
- The code quality gate checks for: length >= 100 chars AND presence of numbered steps.
"""


class DistillationEngine:
    def __init__(self, neo4j: Neo4jClient, llm: LlmClient):
        self._neo4j = neo4j
        self._llm = llm
        self._reg = SkillRegistry(neo4j)

    async def process_pending(self):
        """Process ALL pending reusable_pattern requests in sequence, oldest first."""
        while True:
            records = await self._neo4j.run(
                """MATCH (d:DistillationRequest {status: 'pending', reason: 'reusable_pattern'})
                   RETURN d ORDER BY d.created_at ASC LIMIT 1"""
            )
            if not records:
                break

            d = records[0]["d"]
            sid = d.get("session_id", "")
            try:
                await self._neo4j.run(
                    """MATCH (d:DistillationRequest {session_id: $sid, status: 'pending', reason: 'reusable_pattern'})
                       SET d.status = 'processing'""",
                    {"sid": sid},
                )
                trace = await self._load_trace_since_last(sid, "reusable_pattern", d.get("created_at", ""))
                await self._step(d, trace)
                await self._neo4j.run(
                    """MATCH (d:DistillationRequest {session_id: $sid, status: 'processing', reason: 'reusable_pattern'})
                       SET d.status = 'completed', d.processed_at = datetime()""",
                    {"sid": sid},
                )
            except Exception as e:
                print(f"[Distillation] Error: {e}")
                await self._neo4j.run(
                    "MATCH (d:DistillationRequest {session_id: $sid, reason: 'reusable_pattern'}) SET d.status = 'rejected'",
                    {"sid": sid},
                )

    async def _load_trace_since_last(self, session_id: str, reason: str, current_ts: str) -> str:
        """Load execution steps between last completed request and current request."""
        last = await self._neo4j.run(
            """MATCH (d:DistillationRequest {session_id: $sid, reason: $reason, status: 'completed'})
               RETURN d.processed_at AS ts ORDER BY d.processed_at DESC LIMIT 1""",
            {"sid": session_id, "reason": reason},
        )
        since = last[0]["ts"] if last else None

        query = """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
                   MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)"""
        params: dict = {"sid": session_id}
        conditions = []
        if since:
            conditions.append("step.timestamp >= $since")
            params["since"] = since
        if current_ts:
            conditions.append("step.timestamp <= $until")
            params["until"] = current_ts
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " RETURN step.content AS content ORDER BY step.step_index LIMIT 30"

        records = await self._neo4j.run(query, params)
        lines = []
        for r in records:
            content = r.get("content", "")
            if isinstance(content, str):
                try:
                    for block in json.loads(content):
                        if block.get("type") == "text":
                            lines.append(f"[{block.get('type')}] {block.get('text', '')[:200]}")
                        elif block.get("type") == "tool_result":
                            lines.append(f"[tool:{block.get('name','')}] {block.get('output','')[:150]}")
                except Exception:
                    lines.append(str(content)[:200])
        return "\n".join(lines)

    async def _step(self, request: dict, trace: str):
        skill = await self._find_or_create_skill(request, trace)
        if not skill:
            return
        stage = skill.get("stage", "NL")

        if stage == "NL":
            await self._nl_to_sop(skill, request, trace)
        elif stage == "SOP":
            await self._optimize_or_compile(skill, request, trace)

    async def _find_or_create_skill(self, request: dict, trace: str = "") -> dict | None:
        explicit_id = request.get("skill_id", "")
        sid = request.get("session_id", "")

        if explicit_id:
            records = await self._neo4j.run(
                """MATCH (sk:Skill {skill_id: $skid}) RETURN sk.skill_id AS id, sk.dir AS dir,
                   sk.stage AS stage, sk.name AS name, coalesce(sk.usage_count,0) AS used,
                   coalesce(sk.confidence,0) AS conf, sk.category AS cat""",
                {"skid": explicit_id})
            if records:
                r = records[0]
                return {"id": r["id"], "dir": r["dir"], "stage": r["stage"],
                        "name": r["name"], "usage_count": r["used"], "confidence": r["conf"], "cat": r["cat"]}

        records = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[r:USED_SKILL]->(sk:Skill)
               RETURN sk.skill_id AS id, sk.dir AS dir, sk.stage AS stage,
                      sk.name AS name, coalesce(sk.usage_count,0) AS used,
                      coalesce(sk.confidence,0) AS conf, sk.category AS cat LIMIT 1""",
            {"sid": sid})
        if records:
            r = records[0]
            return {"id": r["id"], "dir": r["dir"], "stage": r["stage"],
                    "name": r["name"], "usage_count": r["used"], "confidence": r["conf"], "cat": r["cat"]}

        # Auto-create NL skill from trace context
        from llm.base import Message as LLMMsg
        summary = request.get("summary", "")
        context = trace[:3000] if trace else summary
        try:
            resp = await self._llm.chat([
                LLMMsg.text_msg(role="user", text=(
                    "Extract skill info from this session trace. Output JSON: "
                    '{"name":"short-name","category":"web_automation|data_processing|system_ops|...","description":"one sentence"}\n'
                    f"Trace: {context}")
                )])
            contents = ''.join([c.text if c.type == "text" and c.text else "" for c in resp.content])
            info = json.loads(contents or "{}")
        except Exception:
            info = {}
        name = info.get("name", summary[:20].strip().lower().replace(" ", "-") or "auto-skill")
        cat = info.get("category", "general")
        desc = info.get("description", summary[:200])
        result = await self._reg.register(name, cat, desc, stage="NL", create_files=True)
        sid_full = result["skill_id"]
        await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid}), (sk:Skill {skill_id: $skid})
               MERGE (s)-[:USED_SKILL]->(sk)""",
            {"sid": sid, "skid": sid_full})
        print(f"[Distillation] Auto-created NL skill: {sid_full}")
        return {"id": sid_full, "dir": result.get("dir", ""), "stage": "NL",
                "name": name, "usage_count": 0, "confidence": 0, "cat": cat}

    async def _nl_to_sop(self, skill: dict, request: dict, trace: str):
        summary = request.get("summary", "")
        try:
            resp = await self._llm.chat([
                Message.text_msg(role="user", text=SOP_PROMPT.format(
                    skill_name=skill.get("name", "unknown"),
                    skill_id=skill.get("id", "unknown"),
                    stage="NL",
                    trace=trace[:3000] if trace else summary,
                    summary=summary))
            ])
            contents = ''.join([c.text if c.type == "text" and c.text else "" for c in resp.content])
            sop_content = (contents or "").strip()
        except Exception as e:
            print(f"[Distillation] LLM error: {e}")
            return

        # Quality gate: must have actual steps, not generic placeholder
        if not sop_content or len(sop_content) < 100:
            print(f"[Distillation] {skill['id']}: SOP content too short, staying NL")
            return
        has_steps = any(trigger in sop_content for trigger in ["1.", "Step 1", "### Steps", "## Core Pattern"])
        if not has_steps:
            print(f"[Distillation] {skill['id']}: SOP lacks executable steps, staying NL")
            return

        md_path = Path(skill["dir"]) / "SKILL.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        header = f"---\nname: {skill.get('name')}\ndescription: {summary[:200]}\ncategory: {skill.get('cat', 'general')}\nstage: \"SOP\"\nversion: 1\n---\n"
        md_path.write_text(header + sop_content, encoding="utf-8")
        await self._reg.update_stage(skill["id"], "SOP")
        print(f"[Distillation] {skill['id']}: NL → SOP")

    async def _optimize_or_compile(self, skill: dict, request: dict, trace: str):
        from skill_system.optimizer import SopOptimizer
        opt = SopOptimizer(self._neo4j, self._llm)
        result = await opt.optimize(skill["id"], trace=trace)

        if result and result.get("suggestions"):
            sop_path = Path(skill["dir"]) / "SKILL.md"
            if sop_path.exists():
                current = sop_path.read_text(encoding="utf-8")
                updates = "\n".join(f"- {s}" for s in result["suggestions"])
                sop_path.write_text(current + f"\n\n## Recent Optimizations\n{updates}")
            print(f"[Distillation] {skill['id']}: SOP optimized ({len(result['suggestions'])} suggestions) — stage stays SOP")
        else:
            # No suggestions means SOP is stable — boost confidence for future compile
            await self._neo4j.run(
                """MATCH (s:Skill {skill_id: $sid})
                   SET s.confidence = coalesce(s.confidence, 0.5) + 0.1,
                       s.updated_at = datetime()""",
                {"sid": skill["id"]})
            print(f"[Distillation] {skill['id']}: SOP stable, confidence boosted")

        # Only compile when SOP is truly stable
        confidence = float(skill.get("confidence", 0))
        usage = int(skill.get("usage_count", 0))
        if confidence >= 0.8 and usage >= 5:
            from skill_system.compiler import SopCompiler
            comp = SopCompiler(self._neo4j, self._llm)
            compile_result = await comp.compile_if_ready(skill["id"])
            if compile_result and compile_result.get("status") == "compiled":
                # Compiler already updates stage to CODE internally
                await self._neo4j.run(
                    """MATCH (s:Skill {skill_id: $sid})
                       SET s.stage = 'CODE', s.updated_at = datetime()""",
                    {"sid": skill["id"]})
                print(f"[Distillation] {skill['id']}: SOP → CODE")
