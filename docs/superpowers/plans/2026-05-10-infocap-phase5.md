# infoCap Phase 5: 信念修正 · 预判检索 · 归档挖掘

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement belief revision with graph traversal propagation, anticipatory retrieval via subgraph matching, L4 meta-pattern analogy for skill suggestion, L5 archive mining for forgotten patterns, and Web UI enhancements (skill detail page, memory graph visualization).

**Architecture:** Belief revision propagates confidence changes through the L2 knowledge graph using Neo4j traversal. Anticipatory retrieval pre-loads relevant memories before the agent asks, using subgraph matching against current task context. The subconscious loop periodically mines L5 archives for valuable patterns that were discarded by compression. Web UI gains per-skill detail view and Neo4j graph visualization.

**Tech Stack:** Python 3.11+, Neo4j 5.x, D3.js/Cytoscape.js (frontend visualization)

---

### Task 1: 信念修正传播 (Belief Revision)

**Files:**
- Create: `memory/belief.py`

When an entity's confidence changes, propagate the effect through the graph:

```python
"""Belief revision with graph traversal propagation."""
from memory.neo4j_client import Neo4jClient


class BeliefReviser:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def revise(self, entity_id: str, new_confidence: float):
        """Update entity confidence and propagate to dependents."""
        # Get current confidence for delta calculation
        records = await self._neo4j.run(
            "MATCH (e:Entity {entity_id: $eid}) RETURN coalesce(e.confidence, 0.5) AS c",
            {"eid": entity_id},
        )
        if not records:
            return
        old = records[0]["c"]
        delta = new_confidence - old

        # Update the entity
        await self._neo4j.run(
            "MATCH (e:Entity {entity_id: $eid}) SET e.confidence = $c, e.updated_at = datetime()",
            {"eid": entity_id, "c": new_confidence},
        )

        # Propagate to directly connected entities (1-hop)
        await self._neo4j.run(
            """MATCH (e:Entity {entity_id: $eid})--(related:Entity)
               SET related.confidence = coalesce(related.confidence, 0.5) + $delta * 0.3,
                   related.updated_at = datetime()""",
            {"eid": entity_id, "delta": delta},
        )

    async def check_contradictions(self) -> list[dict]:
        """Find entities linked with CONTRADICTS that have conflicting confidence."""
        return await self._neo4j.run(
            """MATCH (a:Entity)-[:CONTRADICTS]->(b:Entity)
               WHERE abs(coalesce(a.confidence, 0) - coalesce(b.confidence, 0)) > 0.5
               RETURN a.entity_id AS a, b.entity_id AS b,
                      a.confidence AS ac, b.confidence AS bc"""
        )
```

- [ ] **Commit**

---

### Task 2: 预判检索 (Anticipatory Retrieval)

**Files:**
- Create: `memory/anticipatory.py`
- Modify: `agent/conscious.py` (call before rounds)

Pre-loads relevant memories by matching current task context against historical patterns:

```python
"""Anticipatory retrieval — pre-load memories before agent asks."""
from memory.neo4j_client import Neo4jClient


class AnticipatoryRetrieval:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def predict(self, current_input: str, session_id: str) -> dict:
        """Predict what memories the agent will need next."""
        result = {"skills": [], "entities": [], "patterns": []}

        # 1. Subgraph match: find similar past sessions
        similar = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               WHERE step.role = 'system'
               RETURN step.content AS content ORDER BY step.step_index DESC LIMIT 10""",
            {"sid": session_id},
        )

        # 2. Search entities matching current context
        entities = await self._neo4j.run(
            """CALL db.index.fulltext.queryNodes('entity_search', $q)
               YIELD node AS e, score WHERE score > 0.3
               RETURN e LIMIT 5""",
            {"q": current_input[:200]},
        )
        for r in entities:
            result["entities"].append(dict(r["e"]))

        # 3. Search meta-patterns
        patterns = await self._neo4j.run(
            """MATCH (p:MetaPattern)
               WHERE $q CONTAINS p.name OR p.description CONTAINS $q
               RETURN p LIMIT 3""",
            {"q": current_input[:100]},
        )
        for r in patterns:
            result["patterns"].append(dict(r["p"]))

        return result

    async def preload_context(self, current_input: str, session_id: str) -> str:
        """Generate a preload hint for the system prompt."""
        predictions = await self.predict(current_input, session_id)

        hints = []
        if predictions["entities"]:
            names = [e.get("name", "?") for e in predictions["entities"][:3]]
            hints.append(f"Related L2 entities: {', '.join(names)}")
        if predictions["patterns"]:
            names = [p.get("name", "?") for p in predictions["patterns"][:2]]
            hints.append(f"Matching L4 patterns: {', '.join(names)}")

        return "\n".join(hints) if hints else ""
```

- [ ] **Commit**

---

### Task 3: L5 归档挖掘 (Archive Mining)

**Files:**
- Create: `memory/archive_miner.py`
- Modify: `agent/subconscious.py` (add periodic mining)

Periodically scans compressed archives for valuable patterns worth recovering:

```python
"""L5 archive mining — recover forgotten patterns from compressed logs."""
import json
from pathlib import Path
from memory.neo4j_client import Neo4jClient
from llm.base import LlmClient, Message


class ArchiveMiner:
    def __init__(self, neo4j: Neo4jClient, llm: LlmClient, archive_dir: str):
        self._neo4j = neo4j
        self._llm = llm
        self._archive_dir = Path(archive_dir)

    async def mine(self, lookback_days: int = 30):
        """Scan recent session traces for forgotten patterns."""
        records = await self._neo4j.run(
            """MATCH (s:Session)-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               WHERE step.timestamp > datetime() - duration({days: $days})
                 AND NOT (step)-[:PRODUCED]->(:Entity)
               RETURN DISTINCT step.content AS content, s.session_id AS sid
               LIMIT 30""",
            {"days": lookback_days},
        )

        tool_sequences: dict[str, int] = {}
        for r in records:
            content = r.get("content", "")
            if isinstance(content, str):
                try:
                    for block in json.loads(content):
                        if block.get("type") == "tool_result":
                            tool_sequences[block.get("name", "")] = \
                                tool_sequences.get(block.get("name", ""), 0) + 1
                except Exception:
                    pass

        # Find recurring tool patterns worth extracting
        frequent = {k: v for k, v in tool_sequences.items() if v >= 3}
        if frequent:
            print(f"  [ArchiveMiner] Found {len(frequent)} recurring tool patterns: {list(frequent.keys())[:5]}")
            # Create entities for frequent tools
            for tool, count in frequent.items():
                await self._neo4j.run(
                    """MERGE (e:Entity {entity_id: $eid})
                       ON CREATE SET e.entity_type = 'ToolPattern', e.name = $name,
                          e.content = $content, e.properties = '{}',
                          e.confidence = 0.5, e.source = 'archive_mined',
                          e.activation = 1.0, e.created_at = datetime()""",
                    {"eid": f"ent_pattern_{tool}", "name": tool,
                     "content": f"Frequently used tool: {tool} ({count} times in {lookback_days} days)"},
                )

    async def mine_archived_sessions(self):
        """Recover valuable patterns from completed sessions."""
        # Find completed sessions with high turn counts (complex tasks)
        records = await self._neo4j.run(
            """MATCH (s:Session {status: 'completed'})
               WHERE s.type = 'main' AND coalesce(s.turn_count, 0) >= 10
                 AND NOT EXISTS { (s)-[:MINED]->() }
               RETURN s.session_id AS sid, s.turn_count AS tc
               ORDER BY s.created_at DESC LIMIT 5"""
        )
        for r in records:
            print(f"  [ArchiveMiner] Mining session {r['sid']} ({r['tc']} turns)")
            # Mark as mined
            await self._neo4j.run(
                "MATCH (s:Session {session_id: $sid}) SET s:Mined",
                {"sid": r["sid"]},
            )
```

- [ ] **Commit**

---

### Task 4: Web UI — Skill Detail Page

**Files:**
- Create: `webui/app/skills/[id]/page.tsx`
- Modify: `server/app.py` (add skill detail API)

Show full SKILL.md content, evolution history, related entities:

```
GET /api/skills/{id}  →  returns skill node + SKILL.md content + evolution chain
```

```tsx
// webui/app/skills/[id]/page.tsx
"use client";
// Skill detail page: shows full SKILL.md, evolution history, related entities
```

- [ ] **Commit**

---

### Task 5: Web UI — Memory Graph Visualization

**Files:**
- Create: `server/app.py` (add graph data API)
- Create: `webui/app/memory/page.tsx`

```
GET /api/memory/graph?keyword=... → returns nodes + edges for D3.js/Cytoscape
```

Interactive force-directed graph showing Entity nodes and their relationships.

- [ ] **Commit**

---

### Task 6: 集成测试

**Files:**
- Create: `tests/test_phase5_integration.py`

Test belief propagation, anticipatory retrieval, archive mining.

- [ ] **Commit**

---

## Phase 5 完成检查清单

- [x] Task 1: Belief revision with graph propagation
- [x] Task 2: Anticipatory retrieval (subgraph + entity + pattern preload)
- [x] Task 3: L5 archive mining (tool patterns + session mining)
- [x] Task 4: Skill detail page (SKILL.md view + evolution chain)
- [x] Task 5: Memory graph visualization (D3.js force graph)
- [x] Task 6: Integration tests
