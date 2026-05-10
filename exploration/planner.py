"""Curriculum planner for autonomous skill exploration."""
from memory.neo4j_client import Neo4jClient
from skill_system.scorer import SkillScorer

ALL_KNOWN_CATEGORIES = {
    "web_automation", "data_processing", "code_generation",
    "file_management", "system_ops", "communication",
    "security", "monitoring", "deployment",
}


class ExplorationPlanner:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j
        self._scorer = SkillScorer(neo4j)

    async def plan(self, max_tasks: int = 3) -> list[dict]:
        scores = await self._scorer.score_all()
        cats = await self._neo4j.run(
            "MATCH (c:SkillCategory) RETURN c.name AS name, c.skill_count AS cnt ORDER BY c.skill_count ASC"
        )
        existing_cats = {r["name"] for r in cats}
        tasks = []

        # Deepen: high-score skills
        for s in scores[:5]:
            if s["score"] > 6.0:
                tasks.append({
                    "type": "deepen", "skill_id": s["skill_id"],
                    "name": s["name"], "score": s["score"],
                    "prompt": (
                        f"Practice and improve the skill '{s['name']}' (id: {s['skill_id']}). "
                        f"Find edge cases, try variations, and document solutions. "
                        f"After practice, use skill_manage to update the SOP or create the discovery to long-term memory by start_long_term_update."
                    ),
                })

        # Explore: missing categories
        missing = ALL_KNOWN_CATEGORIES - existing_cats
        for cat in list(missing)[:3]:
            tasks.append({
                "type": "explore", "category": cat, "score": 5.0,
                "prompt": (
                    f"Explore the domain '{cat}'. Research what typical tasks exist in this area, "
                    f"try simple examples using available tools, and register any useful findings. "
                    f"If you discover a reusable workflow, use skill_manage to register a new Skill "
                    f"with category='{cat}'. If you find useful information, record it via "
                    f"start_long_term_update or entity_manage."
                ),
            })

        return tasks[:max_tasks]

    async def get_gap_analysis(self) -> dict:
        cats = await self._neo4j.run(
            "MATCH (c:SkillCategory) RETURN c.name AS name, c.skill_count AS cnt"
        )
        existing = {r["name"]: r["cnt"] for r in cats}
        return {
            "existing": existing,
            "missing": list(ALL_KNOWN_CATEGORIES - set(existing.keys())),
        }
