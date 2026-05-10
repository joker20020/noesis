"""Unified memory retrieval — single entry point for L0-L4."""
from pathlib import Path
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient
from memory.index import L1Index


class MemorySearchTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j
        self._l1 = L1Index(neo4j)

    def schema(self):
        return ToolSchema(
            name="memory_search",
            description=(
                "Unified memory retrieval for L0-L4. "
                "L1 skills are auto-injected in system prompt — no tool call needed. "
                "rag=L2 Entity GraphRAG (local multi-hop or global clustering), "
                "sop=L3 find Skill then load SKILL.md from filesystem, "
                "pattern=L4 MetaPattern search, "
                "load=Skill-associated Entities, "
                "trace=L0 execution step chain, "
                "related=Skill relationships."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["rag", "sop", "pattern", "load", "trace", "related"]},
                    "keyword": {"type": "string", "description": "Search keyword for route/rag/sop/pattern"},
                    "skill_id": {"type": "string", "description": "Target Skill ID for load/trace/related"},
                    "session_id": {"type": "string", "description": "Session ID for trace mode"},
                    "category": {"type": "string", "description": "Filter by Skill/Entity category"},
                    "stage": {"type": "string", "description": "Filter Skill by stage"},
                    "top_k": {"type": "integer", "description": "Max results (default 10)"},
                    "hops": {"type": "integer", "description": "Graph traversal depth for rag (default 1, 0=direct search only)"},
                    "strategy": {"type": "string", "enum": ["local", "global"], "description": "RAG strategy: local=entity traversal, global=category clustering"},
                },
                "required": ["mode"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        mode = call.arguments["mode"]
        try:
            handlers = {
                "rag": self._rag, "sop": self._sop, "pattern": self._pattern,
                "load": self._load, "trace": self._trace, "related": self._related,
            }
            handler = handlers.get(mode)
            if handler:
                return await handler(call)
            return ToolResult(call_id=call.id, name="memory_search", success=False,
                              output="", error=f"Unknown mode: {mode}")
        except Exception as e:
            return ToolResult(call_id=call.id, name="memory_search", success=False,
                              output="", error=str(e))

    # ====== L2 RAG ======
    async def _rag(self, call: ToolCall) -> ToolResult:
        keyword = call.arguments.get("keyword", "")
        hops = call.arguments.get("hops", 1)
        strategy = call.arguments.get("strategy", "local")
        top_k = call.arguments.get("top_k", 10)
        if strategy == "local":
            return await self._rag_local(call.id, keyword, hops, top_k)
        else:
            return await self._rag_global(call.id, keyword, top_k)

    async def _rag_local(self, call_id: str, question: str, hops: int, top_k: int) -> ToolResult:
        """L2 Entity GraphRAG: seed from Entity ft-index, include seeds, then multi-hop traverse."""
        seed_query = """
            CALL db.index.fulltext.queryNodes('entity_search', $q) YIELD node AS entity, score
            RETURN entity.entity_id AS id, score ORDER BY score DESC LIMIT 10
        """
        seeds = await self._neo4j.run(seed_query, {"q": question})
        if not seeds:
            return ToolResult(call_id=call_id, name="memory_search", success=True,
                            output="(No L2 entities found. Use entity_manage to create entities.)")

        seed_ids = [s["id"] for s in seeds]

        # Include seed entities directly
        scored: dict = {}
        for s in seeds:
            props = await self._get_entity_props(s["id"])
            if props:
                score = float(s.get("score", 1.0)) * 2.0 + float(props.get("confidence", 0.5)) * 2.0
                props["_score"] = round(score, 2)
                scored[s["id"]] = props

        # Multi-hop traversal
        neighbor_count = 0
        if hops > 0:
            hop_query = f"""
                MATCH (seed:Entity)-[*1..{hops}]-(related:Entity)
                WHERE seed.entity_id IN $seed_ids
                WITH DISTINCT related RETURN labels(related) AS labels, properties(related) AS props LIMIT 100
            """
            rows = await self._neo4j.run(hop_query, {"seed_ids": seed_ids})
            neighbor_count = len(rows)
            for row in rows:
                props = row["props"]
                nid = props.get("entity_id")
                if nid is None or nid in scored:
                    continue
                conf = float(props.get("confidence", 0.5))
                props["_score"] = round(conf * 2.0 + 0.5, 2)
                scored[nid] = props

        ranked = sorted(scored.values(), key=lambda x: x["_score"], reverse=True)[:top_k]

        lines = [f"## L2 Entity RAG (local, {hops}-hop, top {top_k})"]
        lines.append(f"Query: {question[:200]}")
        lines.append(f"Seeds: {len(seeds)} | Neighbors: {neighbor_count} | Output: {len(ranked)}\n")
        for item in ranked:
            nid = item.get("entity_id", "?")
            etype = item.get("entity_type", "?")
            name = item.get("name", "")[:80]
            content = item.get("content", "")[:120]
            sc = item.get("_score", 0)
            conf = item.get("confidence", "?")
            lines.append(f"- **{nid}** [{etype}] score:{sc} conf:{conf}")
            lines.append(f"  {name}: {content}")
        return ToolResult(call_id=call_id, name="memory_search", success=True, output="\n".join(lines))

    async def _get_entity_props(self, entity_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (e:Entity {entity_id: $eid}) RETURN e", {"eid": entity_id},
        )
        return dict(records[0]["e"]) if records else None

    async def _rag_global(self, call_id: str, question: str, top_k: int) -> ToolResult:
        """L2 Entity clustering by Skill category."""
        query = """
            MATCH (s:Skill)-[:REFERENCES]->(e:Entity)
            WITH s.category AS theme, e.entity_type AS etype,
                 collect(DISTINCT {name: e.name, content: e.content}) AS entities,
                 count(*) AS cnt
            WHERE cnt > 0
            RETURN theme, etype, entities, cnt ORDER BY cnt DESC LIMIT $top_k
        """
        records = await self._neo4j.run(query, {"top_k": top_k})
        lines = [f"## L2 Entity RAG (global, top {top_k})"]
        lines.append(f"Query: {question[:200]}\n")
        if records:
            for r in records:
                lines.append(f"### {r['theme']} / {r['etype']} ({r['cnt']} entities)")
                for e in r["entities"][:5]:
                    lines.append(f"- [{e['etype']}] {e['name']}: {e['content'][:120]}")
        else:
            lines.append("(No entity clusters found.)")
        return ToolResult(call_id=call_id, name="memory_search", success=True, output="\n".join(lines))

    # ====== L3 SOP ======
    async def _sop(self, call: ToolCall) -> ToolResult:
        keyword = call.arguments.get("keyword", "")
        skill_id = call.arguments.get("skill_id", "")
        top_k = call.arguments.get("top_k", 5)
        query = "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED'"
        params: dict = {}
        if skill_id:
            query += " AND s.skill_id = $sid"
            params["sid"] = skill_id
        elif keyword:
            query += " AND (s.name CONTAINS $kw OR s.description CONTAINS $kw OR s.skill_id CONTAINS $kw)"
            params["kw"] = keyword
        query += " RETURN s ORDER BY coalesce(s.activation, 0) DESC LIMIT $top_k"
        params["top_k"] = top_k
        records = await self._neo4j.run(query, params)
        if not records:
            return ToolResult(call_id=call.id, name="memory_search", success=True,
                            output="(No matching Skill found.)")
        lines = [f"Found {len(records)} Skill(s):", ""]
        for r in records:
            s = r["s"]
            lines.append(f"### {s['name']} [{s.get('stage', '?')}] — {s['skill_id']}")
            md_path = Path(s.get("dir", "")) / "SKILL.md"
            if md_path.exists():
                lines.append(md_path.read_text(encoding="utf-8"))
            else:
                lines.append(f"(SKILL.md not found at {md_path})")
            lines.append("---")
        return ToolResult(call_id=call.id, name="memory_search", success=True,
                          output="\n".join(lines))

    # ====== L4 MetaPattern ======
    async def _pattern(self, call: ToolCall) -> ToolResult:
        keyword = call.arguments.get("keyword", "")
        top_k = call.arguments.get("top_k", 10)
        query = """
            MATCH (p:MetaPattern)
            WHERE $q = '' OR p.name CONTAINS $q OR p.description CONTAINS $q
            RETURN p ORDER BY coalesce(p.usage_count, 0) DESC LIMIT $top_k
        """
        records = await self._neo4j.run(query, {"q": keyword, "top_k": top_k})
        lines = [f"## L4 MetaPattern Search (top {top_k})", f"Keyword: {keyword[:200]}\n"]
        if records:
            for r in records:
                p = r["p"]
                lines.append(f"- **{p.get('name', p['pattern_id'])}**: {p.get('description', '')[:200]}")
                steps = p.get("abstract_steps", [])
                if steps:
                    lines.append(f"  Steps: {' -> '.join(steps[:8])}")
                    lines.append(f"  Source: {p.get('source_skills', [])}")
        else:
            lines.append("(No MetaPatterns found. Use meta_pattern to create one.)")
        return ToolResult(call_id=call.id, name="memory_search", success=True, output="\n".join(lines))

    # ====== Other modes ======
    async def _load(self, call: ToolCall) -> ToolResult:
        skill_id = call.arguments["skill_id"]
        query = """
            MATCH (s:Skill {skill_id: $skill_id})
            OPTIONAL MATCH (s)-[:REFERENCES]->(e:Entity)
            RETURN s, collect(DISTINCT e) AS entities
        """
        records = await self._neo4j.run(query, {"skill_id": skill_id})
        if not records:
            return ToolResult(call_id=call.id, name="memory_search", success=False,
                            output="", error=f"Skill not found: {skill_id}")
        return ToolResult(call_id=call.id, name="memory_search", success=True, output=str(records[0]))

    async def _trace(self, call: ToolCall) -> ToolResult:
        session_id = call.arguments["session_id"]
        query = """
            MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
            MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
            RETURN DISTINCT step ORDER BY step.step_index
        """
        records = await self._neo4j.run(query, {"sid": session_id})
        return ToolResult(call_id=call.id, name="memory_search", success=True, output=str(records))

    async def _related(self, call: ToolCall) -> ToolResult:
        skill_id = call.arguments["skill_id"]
        query = """
            MATCH (s:Skill {skill_id: $skill_id})-[r]->(related)
            RETURN type(r) AS rel_type, related
        """
        records = await self._neo4j.run(query, {"skill_id": skill_id})
        return ToolResult(call_id=call.id, name="memory_search", success=True, output=str(records))
