from memory.neo4j_client import Neo4jClient


class MemoryLifecycle:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def decay_all(self, days_threshold: int = 7, rate: float = 0.95, confidence_rate: float = 0.99):
        """Decay activation and confidence for unused nodes. Confidence decays much slower."""
        for label in ["Skill", "Entity", "MetaPattern"]:
            await self._neo4j.run(
                f"""MATCH (n:{label})
                   WHERE (coalesce(n.updated_at, n.created_at) < datetime() - duration({{days: $days}}))
                   SET n.activation = coalesce(n.activation, 1.0) * $rate,
                       n.confidence = coalesce(n.confidence, 0.5) * $crate,
                       n.updated_at = datetime()""",
                {"days": days_threshold, "rate": rate, "crate": confidence_rate},
            )

    async def consolidate_skill(self, skill_id: str, boost: float = 0.2):
        """Boost activation for a used Skill."""
        await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $sid})
               SET s.activation = coalesce(s.activation, 0) + $boost,
                   s.updated_at = datetime()""",
            {"sid": skill_id, "boost": boost},
        )

    async def consolidate_entity(self, entity_id: str, boost: float = 0.2):
        """Boost activation for a used Entity."""
        await self._neo4j.run(
            """MATCH (e:Entity {entity_id: $eid})
               SET e.activation = coalesce(e.activation, 0) + $boost,
                   e.updated_at = datetime()""",
            {"eid": entity_id, "boost": boost},
        )

    async def consolidate_pattern(self, pattern_id: str, boost: float = 0.2):
        """Boost usage for a MetaPattern."""
        await self._neo4j.run(
            """MATCH (p:MetaPattern {pattern_id: $pid})
               SET p.usage_count = coalesce(p.usage_count, 0) + 1""",
            {"pid": pattern_id},
        )

    async def forget_stale(self, activation_threshold: float = 0.1):
        """Deprecate stale Skills, delete abandoned Entities, remove unused MetaPatterns."""
        await self._neo4j.run(
            """MATCH (s:Skill)
               WHERE coalesce(s.activation, 0) < $threshold
               SET s.stage = 'DEPRECATED'""",
            {"threshold": activation_threshold},
        )
        await self._neo4j.run(
            """MATCH (e:Entity)
               WHERE coalesce(e.activation, 0) < $threshold
               DETACH DELETE e""",
            {"threshold": activation_threshold},
        )
        await self._neo4j.run(
            """MATCH (p:MetaPattern)
               WHERE coalesce(p.usage_count, 0) = 0
                 AND (coalesce(p.created_at, datetime()) < datetime() - duration({days: 30}))
               DETACH DELETE p""",
        )

    async def get_stats(self) -> dict:
        skill = await self._neo4j.run(
            "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED' RETURN count(s) AS cnt"
        )
        entity = await self._neo4j.run(
            "MATCH (e:Entity) RETURN count(e) AS cnt"
        )
        meta = await self._neo4j.run(
            "MATCH (p:MetaPattern) RETURN count(p) AS cnt"
        )
        return {
            "skills": skill[0]["cnt"] if skill else 0,
            "entities": entity[0]["cnt"] if entity else 0,
            "patterns": meta[0]["cnt"] if meta else 0,
        }
