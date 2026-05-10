# infoCap Phase 4: Autonomous Exploration 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement autonomous exploration closed loop: curriculum planning via 4D scoring, autonomous task execution in sandbox, result registration to skill tree, and reflection-driven weight adaptation. Add Discord chat platform adapter.

**Architecture:** The subconscious loop triggers exploration during idle time. Curriculum planner uses 4D scores to select the highest-value unexplored skill, then dispatches it to a subagent for autonomous learning. Results are registered as new Skills or Entity nodes. Weight adaptation runs after each exploration cycle, comparing predicted scores against actual usage.

**Tech Stack:** Python 3.11+, Neo4j 5.x, existing Phase 1-3 foundation, discord.py (optional)

---

### Task 1: Autonomous Exploration Engine

**Files:**
- Create: `exploration/__init__.py`
- Create: `exploration/planner.py`

The planner selects which skill to explore next based on 4D scores + gap analysis:

```python
"""Curriculum planner for autonomous skill exploration."""
from memory.neo4j_client import Neo4jClient
from skill_system.scorer import SkillScorer


class ExplorationPlanner:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j
        self._scorer = SkillScorer(neo4j)

    async def plan(self, max_tasks: int = 3) -> list[dict]:
        """Generate prioritized exploration task list."""
        scores = await self._scorer.score_all()
        if not scores:
            return []

        # Get existing skill categories for gap analysis
        cats = await self._neo4j.run(
            """MATCH (c:SkillCategory)
               RETURN c.name AS name, c.skill_count AS cnt
               ORDER BY c.skill_count ASC"""
        )
        existing_cats = {r["name"] for r in cats}

        # Identify category gaps — suggest new categories
        all_known = {"web_automation", "data_processing", "code_generation",
                     "file_management", "system_ops", "communication",
                     "security", "monitoring", "deployment"}

        tasks = []
        # High-score skills → deepen (create variants or compile to code)
        for s in scores[:5]:
            if s["score"] > 6.0:
                tasks.append({
                    "type": "deepen",
                    "skill_id": s["skill_id"],
                    "name": s["name"],
                    "score": s["score"],
                    "prompt": f"Practice and improve the skill '{s['name']}'. "
                              f"Find edge cases and document solutions. "
                              f"Update the SOP with any improvements found.",
                })

        # Missing categories → explore new domains
        missing = all_known - existing_cats
        for cat in list(missing)[:3]:
            tasks.append({
                "type": "explore",
                "category": cat,
                "score": 5.0,
                "prompt": f"Explore the domain '{cat}'. Research common tasks, "
                          f"try simple examples, and register a new Skill.",
            })

        return tasks

    async def get_gap_analysis(self) -> dict:
        """Return category gap analysis for planning."""
        cats = await self._neo4j.run(
            "MATCH (c:SkillCategory) RETURN c.name AS name, c.skill_count AS cnt"
        )
        return {r["name"]: r["cnt"] for r in cats}
```

- [ ] **Commit**

```bash
git add exploration/
git commit -m "feat: add autonomous exploration planner with gap analysis"
```

---

### Task 2: Exploration Executor

**Files:**
- Create: `exploration/executor.py`

Executes exploration tasks in an isolated sandbox using the subagent tool:

```python
"""Execute exploration tasks via subagent in isolated sandbox."""
import uuid
from pathlib import Path
from memory.neo4j_client import Neo4jClient


class ExplorationExecutor:
    def __init__(self, neo4j: Neo4jClient, llm_client, dispatcher, config):
        self._neo4j = neo4j
        self._llm = llm_client
        self._dispatcher = dispatcher
        self._config = config

    async def execute(self, task: dict, max_rounds: int = 20) -> dict:
        """Run one exploration task, return results."""
        session_id = f"explore_{uuid.uuid4().hex[:8]}"
        workspace = Path(self._config.workspace_dir) / "exploration" / session_id
        workspace.mkdir(parents=True, exist_ok=True)

        # Log exploration session
        await self._neo4j.run(
            """CREATE (s:Session {session_id: $sid, type: 'exploration',
               status: 'running', created_at: datetime()})""",
            {"sid": session_id},
        )

        from agent.conscious import ConsciousLoop
        loop = ConsciousLoop(
            llm_client=self._llm,
            dispatcher=self._dispatcher,
            neo4j=self._neo4j,
            config=self._config,
            session_id=session_id,
            workspace_dir=str(workspace),
        )

        try:
            result = await loop.run(task["prompt"], max_rounds=max_rounds)
            status = "completed"
        except Exception as e:
            result = f"Exploration failed: {e}"
            status = "failed"

        await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})
               SET s.status = $status, s.summary = $result""",
            {"sid": session_id, "status": status, "result": result[:500]},
        )

        return {
            "session_id": session_id,
            "task_type": task.get("type"),
            "status": status,
            "result": result[:500],
        }
```

- [ ] **Commit**

```bash
git add exploration/executor.py
git commit -m "feat: add exploration executor with sandbox subagent"
```

---

### Task 3: Exploration → Skill Registration

**Files:**
- Create: `exploration/reflector.py`

After exploration completes, register findings as Skills or Entities:

```python
"""Reflect on exploration results and register learnings."""
from memory.neo4j_client import Neo4jClient
from skill_system.registry import SkillRegistry
from skill_system.scorer import SkillScorer


class ExplorationReflector:
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j
        self._reg = SkillRegistry(neo4j)
        self._scorer = SkillScorer(neo4j)

    async def reflect(self, result: dict):
        """Analyze exploration result and register findings."""
        if result["status"] != "completed":
            return

        # If exploring a new category, register a basic skill
        if result.get("task_type") == "explore":
            cat = result.get("category", "general")
            name = f"{cat}-exploration"
            await self._reg.register(name, cat, f"Auto-explored: {result['result'][:100]}")

        # Adapt scoring weights based on exploration outcome
        await self._adapt_weights()

        # Update category counts
        await self._neo4j.run(
            """MATCH (c:SkillCategory)
               SET c.skill_count = size((c)<-[:BELONGS_TO]-())"""
        )

    async def _adapt_weights(self):
        """Check if predicted scores match reality."""
        scores = await self._scorer.score_all()
        if not scores:
            return

        # Compare top predicted vs actual
        for s in scores[:3]:
            predicted = {"score": s["score"], "dimensions": s["dimensions"]}
            # Phase 4 simplified: check if top skill has been used
            records = await self._neo4j.run(
                "MATCH (s:Skill {skill_id: $sid}) RETURN coalesce(s.usage_count, 0) AS u",
                {"sid": s["skill_id"]},
            )
            actual = records[0]["u"] if records else 0
            await self._scorer.adapt_weights(predicted, actual)

    async def get_exploration_stats(self) -> dict:
        """Return stats on exploration sessions."""
        records = await self._neo4j.run(
            """MATCH (s:Session {type: 'exploration'})
               RETURN s.status AS status, count(*) AS cnt"""
        )
        return {r["status"]: r["cnt"] for r in records}
```

- [ ] **Commit**

```bash
git add exploration/reflector.py
git commit -m "feat: add exploration reflector with weight adaptation"
```

---

### Task 4: Integrate Exploration into Subconscious Loop

**Files:**
- Modify: `agent/subconscious.py`

Add the exploration cycle to the subconscious tick:

```python
# In _tick, add after lifecycle step:
# Step 4: Autonomous exploration (every 3rd tick or when idle)
if self._tick_count % 3 == 0 or trigger == "idle":
    from exploration.planner import ExplorationPlanner
    from exploration.executor import ExplorationExecutor
    from exploration.reflector import ExplorationReflector

    planner = ExplorationPlanner(self._neo4j)
    tasks = await planner.plan(max_tasks=1)
    if tasks:
        print(f"  [Exploration] Planning: {len(tasks)} tasks queued")
        executor = ExplorationExecutor(self._neo4j, self._llm, None, None)
        for task in tasks[:1]:  # Execute at most 1 per tick
            print(f"  [Exploration] Executing: {task['type']} — {task.get('name', task.get('category', ''))}")
            result = await executor.execute(task, max_rounds=15)
            reflector = ExplorationReflector(self._neo4j)
            await reflector.reflect(result)
            stats = await reflector.get_exploration_stats()
            print(f"  [Exploration] Done: {result['status']}, stats: {stats}")
```

- [ ] **Commit**

```bash
git add agent/subconscious.py
git commit -m "feat: integrate autonomous exploration into subconscious loop"
```

---

### Task 5: Discord Adapter (optional, Phase 4 stretch)

**Files:**
- Create: `adapters/__init__.py`
- Create: `adapters/discord.py`

Basic Discord bot adapter for chat platform integration:

```python
"""Discord chat platform adapter."""
import asyncio


class DiscordAdapter:
    def __init__(self, token: str, engine, channel_ids: list[int] | None = None):
        self._token = token
        self._engine = engine
        self._channel_ids = channel_ids or []

    async def start(self):
        """Start Discord bot (requires discord.py)."""
        try:
            import discord
        except ImportError:
            print("[Discord] discord.py not installed, skipping")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready():
            print(f"[Discord] Logged in as {client.user}")

        @client.event
        async def on_message(message):
            if message.author == client.user:
                return
            if self._channel_ids and message.channel.id not in self._channel_ids:
                return
            if message.content.startswith("!"):
                async with message.channel.typing():
                    result = await self._engine.run(
                        message.content[1:].strip(),
                        session_id=f"discord_{message.author.id}_{message.channel.id}",
                    )
                    # Split long responses
                    for chunk in [result[i:i+1900] for i in range(0, len(result), 1900)]:
                        await message.reply(chunk)

        await client.start(self._token)

    async def stop(self):
        pass
```

- [ ] **Commit**

```bash
git add adapters/
git commit -m "feat: add Discord chat platform adapter"
```

---

### Task 6: Integration Test

**Files:**
- Create: `tests/test_phase4_integration.py`

```python
"""Phase 4 integration tests."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS: {name}")
    else: FAIL += 1; print(f"  FAIL: {name} -- {detail}")

async def main():
    global PASS, FAIL
    from agent.config import Config
    from agent.engine import AgentEngine

    config = Config()
    engine = AgentEngine(config)
    await engine.init()

    # 1. Exploration planner
    print("\n[1] Exploration Planner")
    from exploration.planner import ExplorationPlanner
    planner = ExplorationPlanner(engine.neo4j)
    tasks = await planner.plan(max_tasks=5)
    check("planner returns tasks", isinstance(tasks, list), f"count={len(tasks)}")
    if tasks:
        check("tasks have type", all("type" in t for t in tasks))
        check("tasks have prompt", all("prompt" in t for t in tasks))
        print(f"    Task types: {[t['type'] for t in tasks]}")

    gaps = await planner.get_gap_analysis()
    check("gap analysis returns dict", isinstance(gaps, dict))

    # 2. Exploration reflector
    print("\n[2] Exploration Reflector")
    from exploration.reflector import ExplorationReflector
    reflector = ExplorationReflector(engine.neo4j)
    stats = await reflector.get_exploration_stats()
    check("exploration stats", isinstance(stats, dict), str(stats))

    # 3. Weight adaptation
    print("\n[3] Weight Adaptation")
    await reflector._adapt_weights()
    check("weight adaptation no crash", True)

    # 4. Subconscious integration
    print("\n[4] Subconscious + Exploration")
    from agent.subconscious import SubconsciousLoop
    check("subconscious exists", engine._subconscious is not None)
    # Execute one manual tick
    await engine._subconscious._tick("test")
    check("manual tick no crash", True)

    await engine.close()
    print(f"\nResults: {PASS} PASS, {FAIL} FAIL")
    return FAIL == 0

if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
```

- [ ] **Commit**

```bash
git add tests/test_phase4_integration.py
git commit -m "test: add Phase 4 integration tests"
```

---

## Phase 4 完成检查清单

- [ ] Task 1: Exploration planner (4D scoring + gap analysis)
- [ ] Task 2: Exploration executor (sandbox subagent)
- [ ] Task 3: Exploration reflector (register findings + weight adaptation)
- [ ] Task 4: Integration into subconscious loop
- [x] Task 5: Discord adapter (optional)
- [x] Task 6: Integration tests
