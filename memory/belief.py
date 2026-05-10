"""Belief revision with graph traversal propagation — confidence clamped to [0, 1]."""
from memory.neo4j_client import Neo4jClient

CLAMP = "CASE WHEN c > 1.0 THEN 1.0 WHEN c < 0.0 THEN 0.0 ELSE c END"


class BeliefReviser:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def revise(self, entity_id: str, new_confidence: float):
        new_confidence = max(0.0, min(1.0, new_confidence))
        records = await self._neo4j.run(
            "MATCH (e:Entity {entity_id: $eid}) RETURN coalesce(e.confidence, 0.5) AS c",
            {"eid": entity_id},
        )
        if not records:
            return
        old = records[0]["c"]
        delta = new_confidence - old
        if abs(delta) < 0.01:
            return

        # Update this entity
        await self._neo4j.run(
            f"""MATCH (e:Entity {{entity_id: $eid}})
               WITH e, coalesce(e.confidence, 0.5) + $d AS c
               SET e.confidence = {CLAMP}, e.updated_at = datetime()""",
            {"eid": entity_id, "d": delta},
        )
        # Propagate to 1-hop
        await self._neo4j.run(
            f"""MATCH (e:Entity {{entity_id: $eid}})-[r]-(related:Entity)
               WHERE type(r) IN ['SUPPORTS', 'CAUSED_BY', 'DEPENDS_ON', 'RELATES_TO', 'MANAGED_BY']
               WITH related, coalesce(related.confidence, 0.5) + $d * 0.3 AS c
               SET related.confidence = {CLAMP}, related.updated_at = datetime()""",
            {"eid": entity_id, "d": delta},
        )
        print(f"[Belief] {entity_id}: {old:.2f}→{new_confidence:.2f} (propagated to 1-hop)")

    async def on_successful_use(self, entity_id: str):
        await self._neo4j.run(
            f"""MATCH (e:Entity {{entity_id: $eid}})
               WITH e, coalesce(e.confidence, 0.5) + 0.05 AS c
               SET e.confidence = {CLAMP},
                   e.activation = coalesce(e.activation, 1.0) + 0.1,
                   e.updated_at = datetime()""",
            {"eid": entity_id},
        )

    async def check_contradictions(self) -> list[dict]:
        conflicts = await self._neo4j.run(
            """MATCH (a:Entity)-[:CONTRADICTS]->(b:Entity)
               WHERE abs(coalesce(a.confidence, 0) - coalesce(b.confidence, 0)) > 0.4
               RETURN a.entity_id AS a_id, b.entity_id AS b_id,
                      a.created_at AS a_ts, b.created_at AS b_ts"""
        )
        for c in conflicts:
            older = c["a_id"] if (c.get("a_ts") or "") < (c.get("b_ts") or "") else c["b_id"]
            await self._neo4j.run(
                f"""MATCH (e:Entity {{entity_id: $eid}})
                   WITH e, coalesce(e.confidence, 0.5) - 0.2 AS c
                   SET e.confidence = {CLAMP}""",
                {"eid": older})
        return [dict(c) for c in conflicts]
