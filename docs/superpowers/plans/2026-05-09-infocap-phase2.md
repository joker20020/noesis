# infoCap Phase 2: Skill System + Memory Enhancement 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Skill file system structure with auto-generated SKILL.md, enhance L2 Entity CRUD with relationship management, implement memory lifecycle (activation decay/consolidation), and enable L3 SOP creation/linking.

**Architecture:** Skills live in `skills/{category}/{name}/` with SKILL.md as the entry point. The Skill Registry bridges Neo4j Skill nodes and filesystem directories. Memory lifecycle runs as a background task in the subconscious loop. Enhanced `skill_manage` and new `entity_manage` tools give the agent full CRUD over L2/L3.

**Tech Stack:** Python 3.11+, Neo4j 5.x, existing Phase 1 foundation

---

## File Structure (Phase 2 additions)

```
infoCap/
├── skill_system/                  # 🆕 Skill system
│   ├── registry.py                # Skill Registry (Neo4j + filesystem sync)
│   └── template.py                # SKILL.md template generator
├── memory/
│   ├── entities.py                # 🆕 L2 Entity CRUD
│   ├── sop.py                     # 🆕 L3 SOP CRUD
│   └── lifecycle.py               # 🆕 Memory lifecycle (already scaffolded, now implement)
├── tools/
│   ├── skill_manage.py            # 🔧 Enhanced with more actions
│   ├── entity_manage.py           # 🆕 L2 entity management tool
│   └── sop_manage.py              # 🆕 L3 SOP management tool
├── tests/
│   ├── test_skill_system/
│   └── test_memory/
└── skills/                        # 🆕 Runtime-generated skill directories
    └── {category}/{name}/
        └── SKILL.md
```

---

### Task 1: SKILL.md 模板生成器

**Files:**
- Create: `skill_system/__init__.py`
- Create: `skill_system/template.py`
- Create: `tests/test_skill_system/__init__.py`
- Create: `tests/test_skill_system/test_template.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_skill_system/test_template.py
from skill_system.template import generate_skill_md, SKILL_MD_TEMPLATE


def test_template_has_all_sections():
    md = generate_skill_md(
        name="github-pr-research",
        description="Research GitHub pull requests and generate structured reports",
        category="web_automation",
    )
    assert "github-pr-research" in md
    assert "web_automation" in md
    assert "Overview" in md
    assert "When to Use" in md
    assert "Core Pattern" in md
    assert "Quick Reference" in md or "Implementation" in md
    assert "Common Mistakes" in md


def test_template_stage_nl():
    md = generate_skill_md(
        name="test-skill", description="A test skill",
        category="test", stage="NL",
    )
    assert 'stage: "NL"' in md
    assert 'version: 1' in md
    assert "## Overview" in md


def test_template_stage_code():
    md = generate_skill_md(
        name="test-skill", description="A compiled skill",
        category="test", stage="CODE", version=3,
        scripts=["main.py", "fetch.py"],
    )
    assert 'stage: "CODE"' in md
    assert "scripts/main.py" in md
    assert "scripts/fetch.py" in md
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_skill_system/test_template.py -v
```
Expected: FAIL - module not found

- [ ] **Step 3: Write skill_system/template.py**

```python
SKILL_MD_TEMPLATE = """---
name: {name}
description: {description}
category: {category}
stage: "{stage}"
version: {version}
---

# {title}

## Overview
{overview}

## When to Use
- {when_to_use}

## Core Pattern

### Prerequisites
- {prerequisites}

### Steps
{steps}

## Quick Reference

| Step | Tool | Key Parameters |
|------|------|---------------|
{quick_ref}

## Common Mistakes
- {mistakes}
"""


def generate_skill_md(
    name: str,
    description: str,
    category: str,
    stage: str = "NL",
    version: int = 1,
    scripts: list[str] | None = None,
) -> str:
    title = name.replace("-", " ").title()

    if stage == "NL":
        overview = f"Explore and accomplish tasks related to {title}."
        when = f"When the user needs to work with {title}"
        prereq = "(to be determined through execution)"
        steps = "1. (to be determined through execution)"
        mistakes = "(to be learned through execution)"
        quick = "| (pending) | (pending) | (pending) |"
    elif stage == "SOP":
        overview = f"Standardized workflow for {title}."
        when = f"When the user needs to work with {title}"
        prereq = "(documented from execution)"
        steps = "(documented from execution)"
        mistakes = "(documented from execution)"
        quick = "| (pending) | (pending) | (pending) |"
    else:  # CODE
        overview = f"Execute {title} tasks via pre-built scripts."
        when = f"When the user needs to work with {title}"
        prereq = "Scripts are in scripts/ directory"
        script_list = "\n".join(f"- `{s}`" for s in (scripts or []))
        steps = f"Run via code_run:\n{script_list or '(none)'}"
        mistakes = "- API tokens must be configured in environment variables"
        quick = "\n".join(f"| {s} | code_run | -- |" for s in (scripts or ["(none)"]))

    return SKILL_MD_TEMPLATE.format(
        name=name, description=description, category=category,
        stage=stage, version=version, title=title,
        overview=overview, when_to_use=when,
        prerequisites=prereq, steps=steps,
        quick_ref=quick, mistakes=mistakes,
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_skill_system/test_template.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skill_system/ tests/test_skill_system/
git commit -m "feat: add SKILL.md template generator with stage-specific content"
```

---

### Task 2: Skill Registry (Neo4j + filesystem sync)

**Files:**
- Create: `skill_system/registry.py`
- Create: `tests/test_skill_system/test_registry.py`

- [ ] **Step 1: Write registry.py**

```python
from pathlib import Path
from memory.neo4j_client import Neo4jClient
from skill_system.template import generate_skill_md


class SkillRegistry:
    def __init__(self, neo4j: Neo4jClient, skills_dir: str = "./skills"):
        self._neo4j = neo4j
        self._skills_dir = Path(skills_dir)

    def _skill_dir(self, category: str, name: str) -> Path:
        return self._skills_dir / category / name

    async def register(
        self, name: str, category: str, description: str = "",
        stage: str = "NL", create_files: bool = True,
    ) -> dict:
        skill_id = f"{category}/{name}" if "/" not in name else name
        name_only = skill_id.split("/")[-1]
        cat = category
        dir_path = str(self._skill_dir(cat, name_only))

        # Create Neo4j node
        await self._neo4j.run(
            """MERGE (s:Skill {skill_id: $sid})
               ON CREATE SET s.name = $name, s.description = $desc,
                  s.category = $cat, s.stage = $stage, s.version = 1,
                  s.dir = $dir, s.usage_count = 0, s.success_rate = 0.0,
                  s.activation = 1.0, s.confidence = 0.0,
                  s.created_at = datetime()
               ON MATCH SET s.description = $desc""",
            {"sid": skill_id, "name": name_only, "desc": description,
             "cat": cat, "stage": stage, "dir": dir_path},
        )

        # Ensure category node exists
        await self._neo4j.run(
            """MERGE (c:SkillCategory {name: $cat})
               ON CREATE SET c.created_at = datetime()
               WITH c
               MATCH (s:Skill {skill_id: $sid})
               MERGE (s)-[:BELONGS_TO]->(c)
               WITH c, s
               SET c.skill_count = size((c)<-[:BELONGS_TO]-())""",
            {"cat": cat, "sid": skill_id},
        )

        # Create filesystem structure
        if create_files:
            dir_path_obj = self._skill_dir(cat, name_only)
            dir_path_obj.mkdir(parents=True, exist_ok=True)
            md = generate_skill_md(name_only, description, cat, stage)
            (dir_path_obj / "SKILL.md").write_text(md, encoding="utf-8")
            (dir_path_obj / "scripts").mkdir(exist_ok=True)
            (dir_path_obj / "references").mkdir(exist_ok=True)
            (dir_path_obj / "checkpoints").mkdir(exist_ok=True)

        return {"skill_id": skill_id, "dir": dir_path}

    async def get(self, skill_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) RETURN s", {"sid": skill_id},
        )
        return records[0]["s"] if records else None

    async def list_by_category(self, category: str) -> list[dict]:
        records = await self._neo4j.run(
            """MATCH (s:Skill)-[:BELONGS_TO]->(c:SkillCategory {name: $cat})
               RETURN s ORDER BY s.usage_count DESC""",
            {"cat": category},
        )
        return [r["s"] for r in records]

    async def list_categories(self) -> list[dict]:
        records = await self._neo4j.run(
            "MATCH (c:SkillCategory) RETURN c ORDER BY c.skill_count DESC"
        )
        return [r["c"] for r in records]

    async def update_stage(self, skill_id: str, new_stage: str, version: int | None = None):
        v = version if version is not None else "s.version + 1"
        await self._neo4j.run(
            f"MATCH (s:Skill {{skill_id: $sid}}) SET s.stage = $stage, s.version = {v}, s.updated_at = datetime()",
            {"sid": skill_id, "stage": new_stage},
        )

    async def record_usage(self, skill_id: str, success: bool):
        await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $sid})
               SET s.usage_count = coalesce(s.usage_count, 0) + 1,
                   s.activation = coalesce(s.activation, 0) * 1.1,
                   s.success_rate = CASE WHEN $success
                     THEN (coalesce(s.success_rate, 0) * (s.usage_count - 1) + 1.0) / s.usage_count
                     ELSE (coalesce(s.success_rate, 0) * (s.usage_count - 1)) / s.usage_count
                   END""",
            {"sid": skill_id, "success": success},
        )
```

- [ ] **Step 2: Write test**

```python
# tests/test_skill_system/test_registry.py
import pytest
from skill_system.registry import SkillRegistry
from memory.neo4j_client import Neo4jClient
from agent.config import Neo4jConfig


@pytest.mark.asyncio
async def test_register_and_get_skill():
    client = Neo4jClient(Neo4jConfig())
    reg = SkillRegistry(client, skills_dir="./skills")
    try:
        result = await reg.register("test-skill", "test", "A test skill")
        assert result["skill_id"] == "test/test-skill"
        skill = await reg.get("test/test-skill")
        assert skill is not None
        assert skill["stage"] == "NL"
    finally:
        await client.run("MATCH (s:Skill {skill_id: 'test/test-skill'}) DETACH DELETE s")
        await client.run("MATCH (c:SkillCategory {name: 'test'}) DETACH DELETE c")
        await client.close()


@pytest.mark.asyncio
async def test_list_categories():
    client = Neo4jClient(Neo4jConfig())
    reg = SkillRegistry(client, skills_dir="./skills")
    try:
        await reg.register("s1", "cat_a", "skill 1")
        await reg.register("s2", "cat_a", "skill 2")
        await reg.register("s3", "cat_b", "skill 3")
        cats = await reg.list_categories()
        names = [c["name"] for c in cats]
        assert "cat_a" in names
        assert "cat_b" in names
    finally:
        for sid in ["cat_a/s1", "cat_a/s2", "cat_b/s3"]:
            await client.run(f"MATCH (s:Skill {{skill_id: '{sid}'}}) DETACH DELETE s")
        for cat in ["cat_a", "cat_b"]:
            await client.run(f"MATCH (c:SkillCategory {{name: '{cat}'}}) DETACH DELETE c")
        await client.close()


@pytest.mark.asyncio
async def test_record_usage():
    client = Neo4jClient(Neo4jConfig())
    reg = SkillRegistry(client, skills_dir="./skills")
    try:
        await reg.register("usage-test", "test", "usage test")
        await reg.record_usage("test/usage-test", success=True)
        skill = await reg.get("test/usage-test")
        assert skill["usage_count"] == 1
        assert skill["success_rate"] == 1.0
        await reg.record_usage("test/usage-test", success=False)
        skill = await reg.get("test/usage-test")
        assert skill["usage_count"] == 2
        assert skill["success_rate"] == 0.5
    finally:
        await client.run("MATCH (s:Skill {skill_id: 'test/usage-test'}) DETACH DELETE s")
        await client.run("MATCH (c:SkillCategory {name: 'test'}) DETACH DELETE c")
        await client.close()
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_skill_system/test_registry.py -v
```
Expected: PASS (Neo4j required)

- [ ] **Step 4: Commit**

```bash
git add skill_system/registry.py tests/test_skill_system/test_registry.py
git commit -m "feat: add Skill Registry with Neo4j + filesystem sync"
```

---

### Task 3: L2 Entity CRUD 工具

**Files:**
- Create: `memory/entities.py`
- Create: `tools/entity_manage.py`
- Create: `tests/test_memory/test_entities.py`

- [ ] **Step 1: Write memory/entities.py**

```python
from memory.neo4j_client import Neo4jClient


class EntityManager:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def create(self, entity_id: str, entity_type: str, name: str,
                     content: str, properties: dict | None = None,
                     source: str = "execution_verified") -> dict:
        props_json = str(properties or {}).replace("'", "\\'")
        await self._neo4j.run(
            """MERGE (e:Entity {entity_id: $eid})
               ON CREATE SET e.entity_type = $type, e.name = $name,
                  e.content = $content, e.properties = $props,
                  e.confidence = 1.0, e.source = $source,
                  e.activation = 1.0, e.created_at = datetime()
               ON MATCH SET e.content = $content,
                  e.properties = $props, e.updated_at = datetime()""",
            {"eid": entity_id, "type": entity_type, "name": name,
             "content": content, "props": properties or {},
             "source": source},
        )
        return {"entity_id": entity_id}

    async def link(self, from_id: str, relation: str, to_id: str,
                   properties: dict | None = None):
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
        return [r["e"] for r in records]

    async def update_confidence(self, entity_id: str, delta: float):
        await self._neo4j.run(
            """MATCH (e:Entity {entity_id: $eid})
               SET e.confidence = coalesce(e.confidence, 1.0) + $delta,
                   e.updated_at = datetime()""",
            {"eid": entity_id, "delta": delta},
        )

    async def decay_activation(self, days_threshold: int = 7, rate: float = 0.95):
        await self._neo4j.run(
            """MATCH (e:Entity)
               WHERE coalesce(e.updated_at, e.created_at) < datetime() - duration({days: $days})
               SET e.activation = coalesce(e.activation, 1.0) * $rate""",
            {"days": days_threshold, "rate": rate},
        )
```

- [ ] **Step 2: Write tools/entity_manage.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient
from memory.entities import EntityManager


class EntityManageTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._mgr = EntityManager(neo4j)

    def schema(self):
        return ToolSchema(
            name="entity_manage",
            description="Manage L2 knowledge graph entities. Create, search, and link entities with dynamic relationships.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "search", "link", "update_confidence"]},
                    "entity_id": {"type": "string", "description": "Unique entity ID (create/link)"},
                    "entity_type": {"type": "string", "description": "Entity type: Person, Service, API, Config, Error, Fact, etc."},
                    "name": {"type": "string", "description": "Entity name"},
                    "content": {"type": "string", "description": "Human-readable description"},
                    "properties": {"type": "object", "description": "Structured properties dict"},
                    "keyword": {"type": "string", "description": "Search keyword"},
                    "relation": {"type": "string", "description": "Relationship type (link action)"},
                    "target_entity_id": {"type": "string", "description": "Target entity for linking"},
                    "delta": {"type": "number", "description": "Confidence delta (+0.1 or -0.1)"},
                    "source": {"type": "string", "description": "Source: execution_verified, inferred, user_claimed"},
                },
                "required": ["action"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        action = call.arguments["action"]
        try:
            if action == "create":
                return await self._create(call)
            elif action == "search":
                return await self._search(call)
            elif action == "link":
                return await self._link(call)
            elif action == "update_confidence":
                return await self._update_confidence(call)
            return ToolResult(call_id=call.id, name="entity_manage", success=False, output="", error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(call_id=call.id, name="entity_manage", success=False, output="", error=str(e))

    async def _create(self, call: ToolCall) -> ToolResult:
        result = await self._mgr.create(
            entity_id=call.arguments["entity_id"],
            entity_type=call.arguments.get("entity_type", "Fact"),
            name=call.arguments.get("name", call.arguments["entity_id"]),
            content=call.arguments.get("content", ""),
            properties=call.arguments.get("properties"),
            source=call.arguments.get("source", "execution_verified"),
        )
        return ToolResult(call_id=call.id, name="entity_manage", success=True,
                          output=f"Entity {result['entity_id']} created/updated")

    async def _search(self, call: ToolCall) -> ToolResult:
        results = await self._mgr.search(
            keyword=call.arguments.get("keyword", ""),
            entity_type=call.arguments.get("entity_type", ""),
            top_k=call.arguments.get("top_k", 10) if "top_k" in call.arguments else 10,
        )
        lines = [f"Found {len(results)} entities:"]
        for e in results:
            lines.append(f"- [{e.get('entity_type', '?')}] {e.get('name', e['entity_id'])}: {e.get('content', '')[:100]}")
        return ToolResult(call_id=call.id, name="entity_manage", success=True, output="\n".join(lines))

    async def _link(self, call: ToolCall) -> ToolResult:
        await self._mgr.link(
            call.arguments["entity_id"], call.arguments["relation"],
            call.arguments["target_entity_id"],
        )
        return ToolResult(call_id=call.id, name="entity_manage", success=True,
                          output=f"Linked {call.arguments['entity_id']} -[{call.arguments['relation']}]-> {call.arguments['target_entity_id']}")

    async def _update_confidence(self, call: ToolCall) -> ToolResult:
        await self._mgr.update_confidence(call.arguments["entity_id"], call.arguments.get("delta", 0.1))
        return ToolResult(call_id=call.id, name="entity_manage", success=True, output="Confidence updated")
```

- [ ] **Step 3: Write test**

```python
# tests/test_memory/test_entities.py
import pytest
from memory.entities import EntityManager
from memory.neo4j_client import Neo4jClient
from agent.config import Neo4jConfig


@pytest.mark.asyncio
async def test_create_and_search_entity():
    client = Neo4jClient(Neo4jConfig())
    mgr = EntityManager(client)
    try:
        await mgr.create("ent_test_1", "Service", "Neo4j", "Database server",
                          {"host": "10.0.1.50", "port": 7687})
        results = await mgr.search(keyword="Neo4j")
        assert any(r["entity_id"] == "ent_test_1" for r in results)
    finally:
        await client.run("MATCH (e:Entity {entity_id: 'ent_test_1'}) DETACH DELETE e")
        await client.close()


@pytest.mark.asyncio
async def test_link_entities():
    client = Neo4jClient(Neo4jConfig())
    mgr = EntityManager(client)
    try:
        await mgr.create("ent_a", "Person", "Alice", "Engineer")
        await mgr.create("ent_b", "Service", "API", "REST API")
        await mgr.link("ent_a", "MANAGES", "ent_b")
        results = await mgr.search(keyword="Alice")
        assert len(results) > 0
    finally:
        await client.run("MATCH (e:Entity) WHERE e.entity_id IN ['ent_a', 'ent_b'] DETACH DELETE e")
        await client.close()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_memory/test_entities.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory/entities.py tools/entity_manage.py tests/test_memory/test_entities.py
git commit -m "feat: add L2 Entity CRUD manager and entity_manage tool"
```

---

### Task 4: L3 SOP 管理

**Files:**
- Create: `memory/sop.py`
- Create: `tools/sop_manage.py`
- Create: `tests/test_memory/test_sop.py`

- [ ] **Step 1: Write memory/sop.py**

```python
from memory.neo4j_client import Neo4jClient


class SopManager:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def create(self, sop_id: str, skill_id: str, content: str,
                     precondition: str = "", confidence: float = 0.5) -> dict:
        await self._neo4j.run(
            """MERGE (sop:SOP {sop_id: $sid})
               ON CREATE SET sop.content = $content, sop.skill_id = $skill_id,
                  sop.version = 1, sop.precondition = $pre,
                  sop.confidence = $conf, sop.created_at = datetime()
               ON MATCH SET sop.content = $content, sop.updated_at = datetime()""",
            {"sid": sop_id, "skill_id": skill_id, "content": content,
             "pre": precondition, "conf": confidence},
        )
        # Link to Skill
        await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $skill_id}), (sop:SOP {sop_id: $sop_id})
               MERGE (s)-[:HAS_SOP]->(sop)""",
            {"skill_id": skill_id, "sop_id": sop_id},
        )
        return {"sop_id": sop_id}

    async def get(self, sop_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (sop:SOP {sop_id: $sid}) RETURN sop", {"sid": sop_id},
        )
        return records[0]["sop"] if records else None

    async def list_by_skill(self, skill_id: str) -> list[dict]:
        records = await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $sid})-[:HAS_SOP]->(sop:SOP)
               RETURN sop ORDER BY sop.version DESC""",
            {"sid": skill_id},
        )
        return [r["sop"] for r in records]

    async def link_sops(self, from_id: str, relation: str, to_id: str):
        valid = {"DEPENDS_ON", "EXTENDS", "VARIANT_OF", "OPTIMIZES", "COMPOSES"}
        if relation not in valid:
            raise ValueError(f"Invalid SOP relation: {relation}. Must be one of {valid}")
        await self._neo4j.run(
            f"MATCH (a:SOP {{sop_id: $from}}), (b:SOP {{sop_id: $to}})"
            f" MERGE (a)-[:{relation}]->(b)",
            {"from": from_id, "to": to_id},
        )
```

- [ ] **Step 2: Write tools/sop_manage.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient
from memory.sop import SopManager


class SopManageTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._mgr = SopManager(neo4j)

    def schema(self):
        return ToolSchema(
            name="sop_manage",
            description="Manage L3 SOPs (Standard Operating Procedures). Create, view, and link SOPs to Skills.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "get", "list", "link"]},
                    "sop_id": {"type": "string"},
                    "skill_id": {"type": "string"},
                    "content": {"type": "string", "description": "SOP full text with steps"},
                    "precondition": {"type": "string"},
                    "relation": {"type": "string", "enum": ["DEPENDS_ON", "EXTENDS", "VARIANT_OF", "OPTIMIZES", "COMPOSES"]},
                    "target_sop_id": {"type": "string"},
                },
                "required": ["action"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        action = call.arguments["action"]
        try:
            if action == "create":
                r = await self._mgr.create(
                    sop_id=call.arguments["sop_id"],
                    skill_id=call.arguments["skill_id"],
                    content=call.arguments.get("content", ""),
                    precondition=call.arguments.get("precondition", ""),
                )
                return ToolResult(call_id=call.id, name="sop_manage", success=True,
                                  output=f"SOP {r['sop_id']} created and linked to Skill {call.arguments['skill_id']}")
            elif action == "get":
                sop = await self._mgr.get(call.arguments["sop_id"])
                if not sop:
                    return ToolResult(call_id=call.id, name="sop_manage", success=False, output="", error="SOP not found")
                return ToolResult(call_id=call.id, name="sop_manage", success=True, output=str(sop))
            elif action == "list":
                sops = await self._mgr.list_by_skill(call.arguments["skill_id"])
                lines = [f"Found {len(sops)} SOPs for {call.arguments['skill_id']}:"]
                for s in sops:
                    lines.append(f"- v{s.get('version',1)}: {s.get('content','')[:120]}")
                return ToolResult(call_id=call.id, name="sop_manage", success=True, output="\n".join(lines))
            elif action == "link":
                await self._mgr.link_sops(call.arguments["sop_id"], call.arguments["relation"], call.arguments["target_sop_id"])
                return ToolResult(call_id=call.id, name="sop_manage", success=True, output="SOPs linked")
            return ToolResult(call_id=call.id, name="sop_manage", success=False, output="", error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(call_id=call.id, name="sop_manage", success=False, output="", error=str(e))
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_memory/test_sop.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add memory/sop.py tools/sop_manage.py tests/test_memory/test_sop.py
git commit -m "feat: add L3 SOP manager and sop_manage tool"
```

---

### Task 5: 记忆生命周期

**Files:**
- Create: `memory/lifecycle.py` (implement, already scaffolded)
- Create: `tests/test_memory/test_lifecycle.py`

- [ ] **Step 1: Write memory/lifecycle.py**

```python
from memory.neo4j_client import Neo4jClient


class MemoryLifecycle:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def decay_all(self, days_threshold: int = 7, rate: float = 0.95):
        """Decay activation for unused nodes across all layers."""
        await self._neo4j.run(
            """MATCH (s:Skill)
               WHERE (coalesce(s.updated_at, s.created_at) < datetime() - duration({days: $days}))
               SET s.activation = coalesce(s.activation, 1.0) * $rate""",
            {"days": days_threshold, "rate": rate},
        )
        await self._neo4j.run(
            """MATCH (e:Entity)
               WHERE (coalesce(e.updated_at, e.created_at) < datetime() - duration({days: $days}))
               SET e.activation = coalesce(e.activation, 1.0) * $rate""",
            {"days": days_threshold, "rate": rate},
        )

    async def consolidate(self, skill_id: str, boost: float = 0.2):
        """Boost activation for a used Skill."""
        await self._neo4j.run(
            """MATCH (s:Skill {skill_id: $sid})
               SET s.activation = coalesce(s.activation, 0) + $boost,
                   s.updated_at = datetime()""",
            {"sid": skill_id, "boost": boost},
        )

    async def forget_stale(self, activation_threshold: float = 0.1):
        """Remove Skills with very low activation."""
        await self._neo4j.run(
            """MATCH (s:Skill)
               WHERE coalesce(s.activation, 0) < $threshold
               SET s.stage = 'DEPRECATED'""",
            {"threshold": activation_threshold},
        )

    async def get_stats(self) -> dict:
        """Return memory stats for monitoring."""
        skill_count = await self._neo4j.run(
            "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED' RETURN count(s) AS cnt"
        )
        entity_count = await self._neo4j.run(
            "MATCH (e:Entity) RETURN count(e) AS cnt"
        )
        sop_count = await self._neo4j.run(
            "MATCH (s:SOP) RETURN count(s) AS cnt"
        )
        return {
            "skills": skill_count[0]["cnt"] if skill_count else 0,
            "entities": entity_count[0]["cnt"] if entity_count else 0,
            "sops": sop_count[0]["cnt"] if sop_count else 0,
        }
```

- [ ] **Step 2: Write tests**

```python
# tests/test_memory/test_lifecycle.py
import pytest
from memory.lifecycle import MemoryLifecycle
from memory.neo4j_client import Neo4jClient
from agent.config import Neo4jConfig


@pytest.mark.asyncio
async def test_get_stats():
    client = Neo4jClient(Neo4jConfig())
    lc = MemoryLifecycle(client)
    stats = await lc.get_stats()
    assert "skills" in stats
    assert "entities" in stats
    await client.close()


@pytest.mark.asyncio
async def test_decay_and_consolidate():
    client = Neo4jClient(Neo4jConfig())
    lc = MemoryLifecycle(client)
    try:
        await client.run(
            """MERGE (s:Skill {skill_id: 'lifecycle-test'})
               SET s.name='Test', s.category='test', s.stage='NL',
                   s.version=1, s.activation=0.5, s.dir='skills/test/lc-test/',
                   s.created_at=datetime() - duration({days: 30})"""
        )
        await lc.decay_all(days_threshold=7, rate=0.5)
        await lc.consolidate("lifecycle-test", boost=0.3)
        records = await client.run("MATCH (s:Skill {skill_id: 'lifecycle-test'}) RETURN s.activation AS a")
        assert records[0]["a"] > 0.3
    finally:
        await client.run("MATCH (s:Skill {skill_id: 'lifecycle-test'}) DETACH DELETE s")
        await client.close()
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_memory/test_lifecycle.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add memory/lifecycle.py tests/test_memory/test_lifecycle.py
git commit -m "feat: implement memory lifecycle (decay, consolidate, forget, stats)"
```

---

### Task 6: 注册新工具到 Engine

**Files:**
- Modify: `agent/engine.py`

- [ ] **Step 1: Register entity_manage and sop_manage tools**

```python
# In agent/engine.py, add to imports:
from tools.entity_manage import EntityManageTool
from tools.sop_manage import SopManageTool

# In _register_tools, add:
self.dispatcher.register(EntityManageTool(self.neo4j))
self.dispatcher.register(SopManageTool(self.neo4j))
```

- [ ] **Step 2: Verify 14 tools registered**

```bash
uv run python -c "from agent.engine import AgentEngine; from agent.config import Config; e = AgentEngine(Config()); print(sorted(e.dispatcher.tool_names()))"
```
Expected: `['ask_user', 'code_run', 'entity_manage', 'file_patch', 'file_read', 'file_write', 'memory_search', 'skill_manage', 'sop_manage', 'start_long_term_update', 'subagent', 'update_working_checkpoint', 'web_execute_js', 'web_scan']`

- [ ] **Step 3: Commit**

```bash
git add agent/engine.py
git commit -m "feat: register entity_manage and sop_manage tools (now 14 total)"
```

---

### Task 7: 更新系统提示加入新工具指引

**Files:**
- Modify: `agent/context.py`

- [ ] **Step 1: Add entity_manage and sop_manage to memory acquisition workflow**

```python
# In SYSTEM_PROMPT's Memory Acquisition Workflow, add after step 3:
3. memory_search(mode="load", skill_id="...") -> load related Entities, SOPs, and dependencies
4. entity_manage(action="search", keyword="...") -> search L2 knowledge graph
5. sop_manage(action="list", skill_id="...") -> view existing SOPs for a Skill
```

- [ ] **Step 2: Commit**

```bash
git add agent/context.py
git commit -m "feat: update system prompt with entity and SOP workflow guidance"
```

---

### Task 8: 集成测试

**Files:**
- Create: `tests/test_phase2_integration.py`

- [ ] **Step 1: Write integration test**

```python
"""Phase 2 integration tests."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.config import Config
from agent.engine import AgentEngine
from skill_system.registry import SkillRegistry
from memory.entities import EntityManager
from memory.sop import SopManager
from memory.lifecycle import MemoryLifecycle

PASS = FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS: {name}")
    else:
        FAIL += 1; print(f"  FAIL: {name} -- {detail}")


async def test_full_skill_workflow():
    print("\n--- Skill System Workflow ---")
    config = Config()
    engine = AgentEngine(config)
    await engine.init()
    reg = SkillRegistry(engine.neo4j, config.skills_dir)

    # Register skill
    result = await reg.register("test-workflow", "test", "Integration test skill")
    check("skill registered", result["skill_id"] == "test/test-workflow", str(result))

    # Verify filesystem
    p = Path(config.skills_dir) / "test" / "test-workflow" / "SKILL.md"
    check("SKILL.md created", p.exists(), str(p))
    check("SKILL.md has content", "test-workflow" in p.read_text(), "")

    # Verify Neo4j
    skill = await reg.get("test/test-workflow")
    check("skill in Neo4j", skill is not None, str(skill))

    # Record usage
    await reg.record_usage("test/test-workflow", True)
    skill = await reg.get("test/test-workflow")
    check("usage recorded", skill["usage_count"] == 1, str(skill["usage_count"]))

    # Entity CRUD
    em = EntityManager(engine.neo4j)
    await em.create("ent_test", "Config", "Test Config", "Test entity", {"key": "val"})
    results = await em.search(keyword="Test")
    check("entity search", any(r["entity_id"] == "ent_test" for r in results), f"found {len(results)}")

    # SOP
    sm = SopManager(engine.neo4j)
    await sm.create("sop_test", "test/test-workflow", "Step 1: Do X\nStep 2: Do Y")
    sops = await sm.list_by_skill("test/test-workflow")
    check("sop linked", len(sops) > 0, f"count={len(sops)}")

    # Lifecycle
    lc = MemoryLifecycle(engine.neo4j)
    stats = await lc.get_stats()
    check("lifecycle stats", stats["skills"] > 0 and stats["entities"] > 0, str(stats))

    # Tool registry
    names = engine.dispatcher.tool_names()
    for t in ["entity_manage", "sop_manage"]:
        check(f"tool registered: {t}", t in names, "")
    check("total 14 tools", len(names) == 14, f"count={len(names)}")

    # Cleanup
    await engine.neo4j.run("MATCH (s:Skill {skill_id: 'test/test-workflow'}) DETACH DELETE s")
    await engine.neo4j.run("MATCH (e:Entity {entity_id: 'ent_test'}) DETACH DELETE e")
    await engine.neo4j.run("MATCH (s:SOP {sop_id: 'sop_test'}) DETACH DELETE s")
    await engine.neo4j.run("MATCH (c:SkillCategory {name: 'test'}) DETACH DELETE c")
    await engine.close()

    global PASS, FAIL
    print(f"\n  Results: {PASS} PASS, {FAIL} FAIL")
    return FAIL == 0


if __name__ == "__main__":
    success = asyncio.run(test_full_skill_workflow())
    sys.exit(0 if success else 1)
```

- [ ] **Step 2: Run integration test**

```bash
uv run python tests/test_phase2_integration.py
```
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_phase2_integration.py
git commit -m "test: add Phase 2 integration tests"
```

---

## Phase 2 完成检查清单

- [ ] Task 1: SKILL.md template generator
- [ ] Task 2: Skill Registry (Neo4j + filesystem)
- [ ] Task 3: L2 Entity CRUD + entity_manage tool
- [ ] Task 4: L3 SOP management + sop_manage tool
- [ ] Task 5: Memory lifecycle (decay/consolidate/forget)
- [ ] Task 6: Register new tools to Engine (14 total)
- [ ] Task 7: Update system prompt
- [ ] Task 8: Integration tests
