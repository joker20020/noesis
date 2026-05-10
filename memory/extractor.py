"""LLM-powered L2 Entity extraction — one request at a time with trace context + dedup."""
import json
from memory.neo4j_client import Neo4jClient
from llm.base import LlmClient, Message


EXTRACT_PROMPT = """Extract entities and relationships from this execution trace.

Execution trace:
{trace}

Summary from agent: {summary}

Output ONLY valid JSON:
{{"entities": [{{"entity_id":"ent_xxx","entity_type":"Person|Service|Config|Error|...","name":"short name","content":"description","properties":{{"key":"value"}}}}], "relations":[{{"from":"ent_xxx","type":"MANAGES|CAUSED_BY|DEPENDS_ON|...","to":"ent_yyy"}}]}}

entity_type and relation type are free-form. Only extract cross-task-reusable knowledge."""


class EntityExtractor:
    def __init__(self, neo4j: Neo4jClient, llm: LlmClient):
        self._neo4j = neo4j
        self._llm = llm

    async def extract_recent(self):
        while True:
            records = await self._neo4j.run(
                """MATCH (d:DistillationRequest {status: 'pending'})
                   WHERE d.reason IN ['subgoal_completed', 'fault_recovery']
                   RETURN d ORDER BY d.created_at ASC LIMIT 1"""
            )
            if not records:
                break
            d = records[0]["d"]
            sid = d.get("session_id", "")
            reason = d.get("reason", "")
            try:
                await self._neo4j.run(
                    """MATCH (d:DistillationRequest {session_id: $sid, status: 'pending'})
                       WHERE d.reason IN ['subgoal_completed', 'fault_recovery']
                       SET d.status = 'processing'""",
                    {"sid": sid},
                )
                trace = await self._load_trace_since_last(sid, reason, d.get("created_at", ""))
                entity_type = "Finding" if reason == "subgoal_completed" else "ErrorPattern"
                await self._extract(sid, d.get("summary", ""), trace, entity_type)
                await self._neo4j.run(
                    """MATCH (d:DistillationRequest {session_id: $sid, status: 'processing'})
                       WHERE d.reason IN ['subgoal_completed', 'fault_recovery']
                       SET d.status = 'completed', d.processed_at = datetime()""",
                    {"sid": sid},
                )
            except Exception as e:
                print(f"[Extractor] Error: {e}")
                await self._neo4j.run(
                    """MATCH (d:DistillationRequest {session_id: $sid})
                       WHERE d.reason IN ['subgoal_completed', 'fault_recovery']
                       SET d.status = 'rejected'""",
                    {"sid": sid},
                )

    async def _load_trace_since_last(self, session_id: str, reason: str, current_ts: str) -> str:
        last = await self._neo4j.run(
            """MATCH (d:DistillationRequest {session_id: $sid, reason: $reason, status: 'completed'})
               RETURN d.processed_at AS ts ORDER BY d.processed_at DESC LIMIT 1""",
            {"sid": session_id, "reason": reason},
        )
        since = last[0]["ts"] if last else None

        query = """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
                   MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)"""
        params: dict = {"sid": session_id}
        if since:
            query += " WHERE step.timestamp >= $since"; params["since"] = since
        query += " RETURN step.content AS content ORDER BY step.step_index LIMIT 30"
        records = await self._neo4j.run(query, params)
        lines = []
        for r in records:
            content = r.get("content", "")
            if isinstance(content, str):
                try:
                    for block in json.loads(content):
                        if block.get("type") == "text":
                            lines.append(f"[text] {block.get('text', '')[:200]}")
                        elif block.get("type") == "tool_result":
                            lines.append(f"[tool:{block.get('name','')}] {block.get('output','')[:150]}")
                except Exception:
                    lines.append(str(content)[:200])
        return "\n".join(lines)

    async def _extract(self, session_id: str, summary: str, trace: str, entity_type: str):
        if not trace and len(summary) < 20:
            return
        try:
            resp = await self._llm.chat([
                Message(role="user", content=EXTRACT_PROMPT.format(trace=trace[:3000] if trace else summary, summary=summary))
            ])
            data = json.loads(resp.content or "{}")
            if data.get("entities"):
                for ent in data["entities"]:
                    ent.setdefault("entity_type", entity_type)
        except Exception as e:
            print(f"[Extractor] LLM error: {e}")
            return
        for ent in data.get("entities", []):
            await self._upsert_entity(ent, session_id)
        for rel in data.get("relations", []):
            await self._create_relation(rel)

    async def _upsert_entity(self, ent: dict, session_id: str):
        """Create or update — check for duplicates by name+type before creating."""
        eid = ent.get("entity_id", f"ent_{abs(hash(ent.get('name',''))) % 1000000:06d}")
        name = ent.get("name", eid)
        etype = ent.get("entity_type", "Fact")
        props = json.dumps(ent.get("properties", {}), ensure_ascii=False)
        content = ent.get("content", "")

        # Check for existing entity with same name+type
        existing = await self._neo4j.run(
            """MATCH (e:Entity {name: $name, entity_type: $type})
               WHERE e.entity_id <> $eid
               RETURN e.entity_id AS eid, coalesce(e.confidence, 0.7) AS c LIMIT 1""",
            {"name": name, "type": etype, "eid": eid})
        if existing:
            old_id = existing[0]["eid"]
            new_conf = min(1.0, existing[0]["c"] + 0.05)
            await self._neo4j.run(
                """MATCH (e:Entity {entity_id: $oid})
                   SET e.content = $content, e.properties = $props,
                       e.confidence = $conf,
                       e.source_trace = coalesce(e.source_trace, []) + [$trace],
                       e.activation = coalesce(e.activation, 1.0) + 0.1,
                       e.updated_at = datetime()""",
                {"oid": old_id, "content": content, "props": props,
                 "conf": new_conf, "trace": session_id})
            print(f"[Extractor] Merged: {old_id} (conf {existing[0]['c']:.2f}→{new_conf:.2f})")
            return

        await self._neo4j.run(
            """MERGE (e:Entity {entity_id: $eid})
               ON CREATE SET e.entity_type = $type, e.name = $name,
                  e.content = $content, e.properties = $props,
                  e.confidence = 0.7, e.source = 'llm_extracted',
                  e.source_trace = [$trace], e.activation = 1.0,
                  e.created_at = datetime()""",
            {"eid": eid, "type": etype, "name": name, "content": content,
             "props": props, "trace": session_id},
        )

    async def _create_relation(self, rel: dict):
        try:
            await self._neo4j.run(
                f"MATCH (a:Entity {{entity_id: $from}}), (b:Entity {{entity_id: $to}})"
                f" MERGE (a)-[:{rel['type']}]->(b)",
                {"from": rel["from"], "to": rel["to"]})
        except Exception:
            pass
