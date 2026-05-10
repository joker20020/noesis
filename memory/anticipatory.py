"""Anticipatory retrieval — pre-load relevant memories before agent asks."""
import re
from memory.neo4j_client import Neo4jClient


def _safe_lucene(q: str) -> str:
    return re.sub(r'[+\-&|!(){}[\]^"~*?:\\/]', ' ', q)


class AnticipatoryRetrieval:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def predict(self, current_input: str, session_id: str) -> dict:
        result = {"entities": [], "patterns": []}

        # Match entities by keyword
        if len(current_input) > 10:
            records = await self._neo4j.run(
                """CALL db.index.fulltext.queryNodes('entity_search', $q)
                   YIELD node AS e, score WHERE score > 0.3
                   RETURN e LIMIT 5""",
                {"q": _safe_lucene(current_input[:200])},
            )
            for r in records:
                result["entities"].append(dict(r["e"]))

        # Match patterns
        records = await self._neo4j.run(
            """MATCH (p:MetaPattern)
               WHERE $q CONTAINS p.name OR p.description CONTAINS $q
                  OR any(word IN split($q, ' ') WHERE word IN p.applicable_domains)
               RETURN p LIMIT 3""",
            {"q": current_input[:100]},
        )
        for r in records:
            result["patterns"].append(dict(r["p"]))

        return result

    async def preload_hint(self, current_input: str, session_id: str) -> str:
        predictions = await self.predict(current_input, session_id)
        hints = []
        if predictions["entities"]:
            names = [e.get("name", "?") for e in predictions["entities"][:3]]
            hints.append(f"Relevant L2 entities: {', '.join(names)}")
        if predictions["patterns"]:
            names = [p.get("name", "?") for p in predictions["patterns"][:2]]
            hints.append(f"Matching L4 patterns: {', '.join(names)}")
        return "\n".join(hints) if hints else ""
