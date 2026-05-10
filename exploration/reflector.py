"""Reflect on exploration results and register learnings with LLM-generated content."""
import json
from memory.neo4j_client import Neo4jClient
from skill_system.registry import SkillRegistry
from skill_system.scorer import SkillScorer
from llm.base import LlmClient, Message


EXPLORE_SKILL_PROMPT = """An autonomous exploration session just completed. Generate a new Skill based on the findings.

Exploration result:
{result}

Output ONLY JSON:
{{"name": "short-name", "category": "{category}", "description": "one sentence", "content": "full SKILL.md in markdown with sections: ## Overview, ## When to Use, ## Core Pattern (with numbered steps using specific tools), ## Common Mistakes"}}

The SKILL.md must reference actual tools (code_run, file_read, web_scraper, memory_search, etc.) with concrete parameters."""


class ExplorationReflector:
    def __init__(self, neo4j: Neo4jClient, llm: LlmClient = None):
        self._neo4j = neo4j
        self._reg = SkillRegistry(neo4j)
        self._scorer = SkillScorer(neo4j)
        self._llm = llm

    async def reflect(self, result: dict):
        if result["status"] != "completed":
            return

        if result.get("task_type") == "explore" and result.get("category"):
            cat = result["category"]
            content = ""
            desc = ""
            name = f"{cat}-auto"

            if self._llm:
                try:
                    resp = await self._llm.chat([
                        Message.text_msg("user", EXPLORE_SKILL_PROMPT.format(
                            category=cat, result=result.get("result", "")[:2000]))
                    ])
                    contents = ''.join([c.text if c.type == "text" and c.text else "" for c in resp.content])
                    info = json.loads(contents or "{}")
                    name = info.get("name", name)
                    desc = info.get("description", f"Auto-explored: {result['result'][:200]}")
                    content = info.get("content", "")
                except Exception as e:
                    print(f"[Reflector] LLM failed: {e}")
                    return  # Skip if LLM can't generate content

            # Only register if LLM generated real content (not template)
            if not content or len(content) < 50:
                print(f"[Reflector] Skipping {name}: LLM content too short ({len(content)} chars)")
                return

            try:
                await self._reg.register(name, cat, desc, stage="NL",
                                         create_files=True, skill_md_content=content)
                print(f"[Reflector] Registered exploration skill: {cat}/{name}")
            except Exception as e:
                print(f"[Reflector] Registration failed: {e}")

        await self._update_category_counts()
        await self._adapt_weights()

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
