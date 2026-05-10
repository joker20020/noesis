"""L5 archive mining — recover forgotten patterns from session traces."""
import json
from memory.neo4j_client import Neo4jClient


class ArchiveMiner:
    def __init__(self, neo4j: Neo4jClient, lookback_days: int = 30):
        self._neo4j = neo4j

    async def mine(self, lookback_days: int = 30):
        """Scan recent tool patterns and create entities for recurring ones."""
        records = await self._neo4j.run(
            """MATCH (s:Session)-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               WHERE step.timestamp > datetime() - duration({days: $days})
                 AND step.role = 'system'
               RETURN DISTINCT step.content AS content
               LIMIT 50""",
            {"days": lookback_days},
        )

        tool_counts: dict[str, int] = {}
        for r in records:
            content = r.get("content", "")
            if isinstance(content, str):
                try:
                    for block in json.loads(content):
                        if block.get("type") == "tool_result":
                            name = block.get("name", "")
                            tool_counts[name] = tool_counts.get(name, 0) + 1
                except Exception:
                    pass

        frequent = {k: v for k, v in tool_counts.items() if v >= 3}
        if frequent:
            for tool, count in frequent.items():
                await self._neo4j.run(
                    """MERGE (e:Entity {entity_id: $eid})
                       ON CREATE SET e.entity_type = 'ToolPattern', e.name = $name,
                          e.content = $content, e.properties = '{}',
                          e.confidence = 0.5, e.source = 'archive_mined',
                          e.activation = 1.0, e.created_at = datetime()
                       ON MATCH SET e.activation = coalesce(e.activation, 1.0) + 0.1""",
                    {"eid": f"ent_pattern_{tool.replace(' ', '_')}",
                     "name": tool,
                     "content": f"Frequently used tool in {lookback_days}d: {tool} ({count} occurrences)"},
                )
            return list(frequent.keys())
        return []
