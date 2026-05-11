"""Reflect on exploration results and register learnings with LLM-generated content.

Two-phase reflection:
  1. STRUCTURED EXTRACTION — LLM extracts findings with type, evidence, and reusability score.
  2. QUALITY FILTER & REGISTER — Only high-quality findings (score >= 6) are registered.
"""
import json
from memory.neo4j_client import Neo4jClient
from skill_system.registry import SkillRegistry
from skill_system.scorer import SkillScorer
from llm.base import LlmClient, Message


# ---------------------------------------------------------------------------
# Phase 1: Structured extraction prompt
# ---------------------------------------------------------------------------
_EXTRACT_FINDINGS_PROMPT = """Analyze the following autonomous exploration session and extract structured findings.

Exploration Task:
- Type: {task_type}
- Goal: {goal}
- Method: {method}
- Success Criteria: {success_criteria}

Exploration Result:
{result}

Instructions:
1. Read the result carefully and identify ALL meaningful discoveries.
2. For each discovery, classify it into one of these types:
   - "tool_pattern": A new way to use an existing tool, or a tool combination that works well
   - "error_recovery": A strategy to recover from a specific error or failure mode
   - "workflow": A reusable multi-step process for a common task
   - "cross_domain": A pattern that applies across multiple skill categories
3. Rate each discovery's reusability (1-10) based on:
   - How general is it? (specific=1, broadly applicable=10)
   - How often will this situation recur?
   - How much value does it provide when reused?
4. Provide concrete evidence (quote specific tool calls, outputs, or observations from the result).

Output ONLY a JSON array. No markdown, no explanation outside JSON.
[
  {
    "type": "tool_pattern|error_recovery|workflow|cross_domain",
    "title": "Short descriptive title (3-6 words)",
    "description": "One sentence explaining what was discovered",
    "evidence": "Concrete evidence from the exploration result",
    "reusability_score": 7,
    "tools_involved": ["tool_name_1", "tool_name_2"],
    "category": "suggested_skill_category"
  }
]

If no meaningful findings exist, output: []"""


# ---------------------------------------------------------------------------
# Phase 2: Skill generation prompt (only for high-quality findings)
# ---------------------------------------------------------------------------
_GENERATE_SKILL_PROMPT = """Generate a Skill document for the following exploration finding.

Finding:
{finding_json}

Exploration Context:
- Task Type: {task_type}
- Goal: {goal}

Output ONLY JSON:
{{
  "name": "short-kebab-case-name",
  "category": "{category}",
  "description": "One sentence",
  "content": "Full SKILL.md markdown with sections:\n## Overview\n## When to Use\n## Prerequisites\n## Core Pattern (numbered steps with specific tool calls and parameters)\n## Error Handling\n## Example (concrete input/output)\n## Related Skills"
}}

Rules for the SKILL.md:
1. Every step must reference actual tools with concrete parameter examples.
2. Include error handling for at least one common failure mode.
3. The Example section must show realistic input and expected output.
4. Keep it actionable — a future instance of the agent should be able to follow it without guessing."""


class ExplorationReflector:
    def __init__(self, neo4j: Neo4jClient, llm: LlmClient = None):
        self._neo4j = neo4j
        self._reg = SkillRegistry(neo4j)
        self._scorer = SkillScorer(neo4j)
        self._llm = llm

    async def reflect(self, result: dict):
        if result["status"] != "completed":
            print(f"[Reflector] Skipping {result.get('session_id')}: session failed")
            return

        if not self._llm:
            print("[Reflector] No LLM available, skipping reflection")
            return

        # ------------------------------------------------------------------
        # Phase 1: Structured extraction
        # ------------------------------------------------------------------
        findings = await self._extract_findings(result)
        if not findings:
            print(f"[Reflector] No findings extracted from {result.get('session_id')}")
            return

        print(f"[Reflector] Extracted {len(findings)} findings from {result.get('session_id')}")

        # ------------------------------------------------------------------
        # Phase 2: Quality filter + register
        # ------------------------------------------------------------------
        registered = 0
        skipped = 0
        for finding in findings:
            score = finding.get("reusability_score", 0)
            if score < 6:
                print(f"[Reflector] Skipping '{finding.get('title')}': reusability score {score} < 6")
                skipped += 1
                continue

            # Deduplication check
            is_duplicate = await self._is_duplicate(finding)
            if is_duplicate:
                print(f"[Reflector] Skipping '{finding.get('title')}': duplicate detected")
                skipped += 1
                continue

            # Generate skill content
            skill_data = await self._generate_skill(result, finding)
            if not skill_data:
                skipped += 1
                continue

            # Register
            try:
                await self._reg.register(
                    name=skill_data["name"],
                    category=skill_data["category"],
                    description=skill_data["description"],
                    stage="NL",
                    create_files=True,
                    skill_md_content=skill_data["content"],
                )
                print(f"[Reflector] Registered exploration skill: {skill_data['category']}/{skill_data['name']} "
                      f"(reusability={score}, type={finding.get('type')})")
                registered += 1
            except Exception as e:
                print(f"[Reflector] Registration failed for '{finding.get('title')}': {e}")
                skipped += 1

        # Update metadata
        await self._update_category_counts()
        await self._adapt_weights()

        print(f"[Reflector] Summary: {registered} registered, {skipped} skipped")

    # ------------------------------------------------------------------
    # Phase 1 implementation
    # ------------------------------------------------------------------

    async def _extract_findings(self, result: dict) -> list[dict]:
        prompt = _EXTRACT_FINDINGS_PROMPT.format(
            task_type=result.get("task_type", "unknown"),
            goal=result.get("goal", ""),
            method=result.get("method", ""),
            success_criteria=result.get("success_criteria", ""),
            result=result.get("result", "")[:3000],
        )
        try:
            resp = await self._llm.chat([Message.text_msg("user", prompt)])
            texts = "".join(
                c.text if c.type == "text" and c.text else ""
                for c in resp.content
            )
            # Handle markdown code blocks
            raw = texts.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
            findings = json.loads(raw or "[]")
            if not isinstance(findings, list):
                return []
            return findings
        except Exception as e:
            print(f"[Reflector] Extraction failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Phase 2 implementation
    # ------------------------------------------------------------------

    async def _is_duplicate(self, finding: dict) -> bool:
        """Check if a similar skill already exists."""
        title = finding.get("title", "")
        description = finding.get("description", "")
        category = finding.get("category", "")

        # Query by exact title match in category
        records = await self._neo4j.run(
            """MATCH (s:Skill)-[:BELONGS_TO]->(c:SkillCategory {name: $cat})
               WHERE toLower(s.name) = toLower($title)
               RETURN s.skill_id AS sid LIMIT 1""",
            {"cat": category, "title": title.replace(" ", "-")},
        )
        if records:
            return True

        # Query by description similarity (fulltext)
        try:
            records = await self._neo4j.run(
                """CALL db.index.fulltext.queryNodes('skill_search', $desc)
                   YIELD node, score
                   WHERE score > 2.0
                   RETURN node.skill_id AS sid LIMIT 1""",
                {"desc": description[:50]},
            )
            if records:
                return True
        except Exception:
            pass  # Fulltext index may not exist

        return False

    async def _generate_skill(self, result: dict, finding: dict) -> dict | None:
        prompt = _GENERATE_SKILL_PROMPT.format(
            finding_json=json.dumps(finding, ensure_ascii=False, indent=2),
            task_type=result.get("task_type", "unknown"),
            goal=result.get("goal", ""),
            category=finding.get("category", "general"),
        )
        try:
            resp = await self._llm.chat([Message.text_msg("user", prompt)])
            texts = "".join(
                c.text if c.type == "text" and c.text else ""
                for c in resp.content
            )
            raw = texts.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
            data = json.loads(raw or "{}")

            # Validate required fields
            if not data.get("name") or not data.get("content"):
                print(f"[Reflector] Generated skill missing name or content for '{finding.get('title')}'")
                return None
            if len(data.get("content", "")) < 100:
                print(f"[Reflector] Generated skill content too short ({len(data.get('content', ''))} chars)")
                return None

            return data
        except Exception as e:
            print(f"[Reflector] Skill generation failed for '{finding.get('title')}': {e}")
            return None

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def _update_category_counts(self):
        await self._neo4j.run(
            """MATCH (c:SkillCategory)
               OPTIONAL MATCH (s:Skill)-[:BELONGS_TO]->(c)
               WITH c, count(s) AS cnt
               SET c.skill_count = cnt"""
        )

    async def _adapt_weights(self):
        scores = await self._scorer.score_all()
        if not scores:
            return
        for s in scores[:3]:
            records = await self._neo4j.run(
                "MATCH (sk:Skill {skill_id: $sid}) RETURN coalesce(sk.usage_count, 0) AS u",
                {"sid": s["skill_id"]},
            )
            actual = records[0]["u"] if records else 0
            predicted = {"score": s["score"], "dimensions": s["dimensions"]}
            await self._scorer.adapt_weights(predicted, actual)

    async def get_exploration_stats(self) -> dict:
        records = await self._neo4j.run(
            "MATCH (s:Session {type: 'exploration'}) RETURN s.status AS st, count(*) AS cnt"
        )
        return {r["st"]: r["cnt"] for r in records}
