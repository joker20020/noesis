from memory.neo4j_client import Neo4jClient
from memory.graph_models import Skill


def _row_to_skill(props: dict) -> Skill:
    return Skill(
        skill_id=props.get("skill_id", ""),
        name=props.get("name", ""),
        description=props.get("description", ""),
        category=props.get("category", ""),
        stage=props.get("stage", "NL"),
        version=props.get("version", 1),
        dir=props.get("dir", ""),
        usage_count=props.get("usage_count", 0),
        success_rate=props.get("success_rate", 0.0),
        activation=props.get("activation", 1.0),
        confidence=props.get("confidence", 0.0),
        context_tags=props.get("context_tags", []),
        embeddings=props.get("embeddings", []),
        created_at=props.get("created_at", ""),
        updated_at=props.get("updated_at", ""),
    )


class L1Index:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def search(self, category: str | None = None, stage: str | None = None,
                     keyword: str | None = None, context_tags: list[str] | None = None,
                     top_k: int = 5) -> list[Skill]:
        query = "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED'"
        params: dict = {}
        if category:
            query += " AND s.category = $category"
            params["category"] = category
        if stage:
            query += " AND s.stage = $stage"
            params["stage"] = stage
        if keyword:
            query += " AND (s.name CONTAINS $kw OR s.skill_id CONTAINS $kw OR s.description CONTAINS $kw)"
            params["kw"] = keyword
        if context_tags:
            for i, tag in enumerate(context_tags):
                query += f" AND $tag_{i} IN s.context_tags"
                params[f"tag_{i}"] = tag
        query += " RETURN s ORDER BY coalesce(s.activation, 0) DESC, coalesce(s.usage_count, 0) DESC LIMIT $top_k"
        params["top_k"] = top_k
        records = await self._neo4j.run(query, params)
        return [_row_to_skill(r["s"]) for r in records]

    async def get(self, skill_id: str) -> Skill | None:
        records = await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) RETURN s", {"sid": skill_id},
        )
        return _row_to_skill(records[0]["s"]) if records else None

    async def update_activation(self, skill_id: str, delta: float):
        await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) SET s.activation = coalesce(s.activation, 0) + $delta",
            {"sid": skill_id, "delta": delta},
        )

    async def decay(self, days_threshold: int = 7, rate: float = 0.95):
        await self._neo4j.run(
            """MATCH (s:Skill)
               WHERE (coalesce(s.updated_at, s.created_at) < datetime() - duration({days: $days}))
               SET s.activation = coalesce(s.activation, 1.0) * $rate""",
            {"days": days_threshold, "rate": rate},
        )
