import json
from memory.neo4j_client import Neo4jClient


class EntityManager:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def create(self, entity_id: str, entity_type: str, name: str,
                     content: str, properties: dict | None = None,
                     source: str = "execution_verified") -> dict:
        props_json = json.dumps(properties or {}, ensure_ascii=False)
        await self._neo4j.run(
            """MERGE (e:Entity {entity_id: $eid})
               ON CREATE SET e.entity_type = $type, e.name = $name,
                  e.content = $content, e.properties = $props,
                  e.confidence = 1.0, e.source = $source,
                  e.activation = 1.0, e.created_at = datetime()
               ON MATCH SET e.content = $content,
                  e.properties = $props, e.updated_at = datetime()""",
            {"eid": entity_id, "type": entity_type, "name": name,
             "content": content, "props": props_json, "source": source},
        )
        return {"entity_id": entity_id}

    def _parse_props(self, e: dict) -> dict:
        props = e.get("properties", {})
        if isinstance(props, str):
            try:
                return json.loads(props)
            except (json.JSONDecodeError, TypeError):
                return {}
        return props or {}

    async def link(self, from_id: str, relation: str, to_id: str):
        await self._neo4j.run(
            f"MATCH (a:Entity {{entity_id: $from}}), (b:Entity {{entity_id: $to}})"
            f" MERGE (a)-[:{relation}]->(b)",
            {"from": from_id, "to": to_id},
        )

    async def search(self, keyword: str = "", entity_type: str = "",
                     top_k: int = 10) -> list[dict]:
        query = "MATCH (e:Entity) WHERE 1=1"
        params: dict = {}
        if keyword:
            query += " AND (e.name CONTAINS $kw OR e.content CONTAINS $kw)"
            params["kw"] = keyword
        if entity_type:
            query += " AND e.entity_type = $type"
            params["type"] = entity_type
        query += " RETURN e ORDER BY coalesce(e.activation, 0) DESC LIMIT $top_k"
        params["top_k"] = top_k
        records = await self._neo4j.run(query, params)
        results = []
        for r in records:
            e = dict(r["e"])
            e["properties"] = self._parse_props(e)
            results.append(e)
        return results

    async def update(self, entity_id: str, name: str = None, content: str = None,
                     entity_type: str = None, properties: dict = None):
        sets = []
        params: dict = {"eid": entity_id}
        if name is not None:
            sets.append("e.name = $name"); params["name"] = name
        if content is not None:
            sets.append("e.content = $content"); params["content"] = content
        if entity_type is not None:
            sets.append("e.entity_type = $type"); params["type"] = entity_type
        if properties is not None:
            sets.append("e.properties = $props")
            params["props"] = json.dumps(properties, ensure_ascii=False)
        if sets:
            sets.append("e.updated_at = datetime()")
            await self._neo4j.run(
                f"MATCH (e:Entity {{entity_id: $eid}}) SET {', '.join(sets)}", params)

    async def delete(self, entity_id: str):
        await self._neo4j.run(
            "MATCH (e:Entity {entity_id: $eid}) DETACH DELETE e", {"eid": entity_id})

    async def get(self, entity_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (e:Entity {entity_id: $eid}) RETURN e", {"eid": entity_id})
        if records:
            e = dict(records[0]["e"])
            e["properties"] = self._parse_props(e)
            return e
        return None

    async def update_confidence(self, entity_id: str, delta: float):
        await self._neo4j.run(
            """MATCH (e:Entity {entity_id: $eid})
               WITH e, coalesce(e.confidence, 1.0) + $d AS c
               SET e.confidence = CASE WHEN c > 1.0 THEN 1.0 WHEN c < 0.0 THEN 0.0 ELSE c END,
                   e.updated_at = datetime()""",
            {"eid": entity_id, "d": delta},
        )
