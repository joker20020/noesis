"""L4 Meta-Pattern: cross-domain abstract strategies extracted from Skills."""
from memory.neo4j_client import Neo4jClient


class MetaPatternManager:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def create(self, pattern_id: str, name: str, description: str,
                     abstract_steps: list[str] | None = None,
                     source_skills: list[str] | None = None) -> dict:
        await self._neo4j.run(
            """MERGE (p:MetaPattern {pattern_id: $pid})
               ON CREATE SET p.name = $name, p.description = $desc,
                  p.abstract_steps = $steps, p.source_skills = $sources,
                  p.usage_count = 0, p.created_at = datetime()
               ON MATCH SET p.description = $desc,
                  p.abstract_steps = $steps, p.source_skills = $sources""",
            {"pid": pattern_id, "name": name, "desc": description,
             "steps": abstract_steps or [], "sources": source_skills or []},
        )
        # Link source skills to pattern
        for sid in (source_skills or []):
            await self._neo4j.run(
                """MATCH (s:Skill {skill_id: $sid}), (p:MetaPattern {pattern_id: $pid})
                   MERGE (s)-[:INSTANTIATES]->(p)""",
                {"sid": sid, "pid": pattern_id},
            )
        return {"pattern_id": pattern_id}

    async def extract_from_skills(self, category: str = "") -> list[dict]:
        """Find common patterns across Skills in the same category.

        Phaes 2 (basic): group Skills with shared keywords in their descriptions.
        Phase 5 (TODO): use GDS node similarity or LLM-based pattern extraction.
        """
        query = """MATCH (s:Skill) WHERE s.stage IN ['SOP', 'CODE']"""
        params: dict = {}
        if category:
            query += " AND s.category = $cat"
            params["cat"] = category
        query += " RETURN s.skill_id AS id, s.name AS name, s.description AS desc, s.category AS cat"
        records = await self._neo4j.run(query, params)
        # Group by shared keywords (basic heuristic)
        groups: dict[str, list[dict]] = {}
        for r in records:
            desc_words = set(r["desc"].lower().split())
            name_words = set(r["name"].lower().split())
            shared = desc_words & name_words
            key = r["cat"] + "/" + ("_".join(sorted(shared)[:3]) if shared else "general")
            groups.setdefault(key, []).append(r)
        # Merge small groups into category-level groups
        merged: dict[str, list[dict]] = {}
        for key, members in groups.items():
            if len(members) >= 2:
                merged[key] = members
            else:
                cat_key = key.split("/")[0] + "/_category"
                merged.setdefault(cat_key, []).extend(members)
        patterns = []
        for key, members in merged.items():
            if len(members) >= 2:
                patterns.append({
                    "key": key,
                    "skill_count": len(members),
                    "skill_ids": [m["id"] for m in members],
                    "names": [m["name"] for m in members],
                })
        return patterns

    async def search(self, keyword: str = "", top_k: int = 10) -> list[dict]:
        query = "MATCH (p:MetaPattern) WHERE 1=1"
        params: dict = {}
        if keyword:
            query += " AND (p.name CONTAINS $kw OR p.description CONTAINS $kw)"
            params["kw"] = keyword
        query += " RETURN p ORDER BY p.usage_count DESC LIMIT $top_k"
        params["top_k"] = top_k
        records = await self._neo4j.run(query, params)
        return [r["p"] for r in records]

    async def apply_pattern(self, pattern_id: str):
        """Record usage of a pattern (for ranking)."""
        await self._neo4j.run(
            "MATCH (p:MetaPattern {pattern_id: $pid}) SET p.usage_count = coalesce(p.usage_count, 0) + 1",
            {"pid": pattern_id},
        )
