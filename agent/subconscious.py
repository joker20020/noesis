"""Subconscious loop — background tasks for memory evolution."""
import asyncio
import time
from datetime import datetime
from memory.neo4j_client import Neo4jClient
from memory.lifecycle import MemoryLifecycle
from agent.config import Config


class SubconsciousLoop:
    def __init__(self, neo4j: Neo4jClient, config: Config, llm_client, dispatcher=None):
        self._neo4j = neo4j
        self._config = config
        self._llm = llm_client
        self._dispatcher = dispatcher
        self._lifecycle = MemoryLifecycle(neo4j)
        self._idle_seconds = config.subconscious_idle_seconds
        self._timer_seconds = config.subconscious_timer_seconds
        self._running = False
        self._last_activity = time.time()
        self._tick_count = 0

    def touch(self):
        self._last_activity = time.time()

    async def start(self):
        self._running = True
        print(f"[Subconscious] Started — idle trigger: {self._idle_seconds}s, timer: {self._timer_seconds}s")
        while self._running:
            await asyncio.sleep(60)
            now = time.time()
            elapsed = now - self._last_activity
            is_idle = elapsed > self._idle_seconds
            is_periodic = int(now) % self._timer_seconds < 60

            if is_idle or is_periodic:
                trigger = "idle" if is_idle else "timer"
                try:
                    await self._tick(trigger)
                    self._last_activity = time.time()  # Reset after tick
                except Exception as e:
                    print(f"[Subconscious] ❌ Error: {e}")

    def stop(self):
        self._running = False
        print(f"[Subconscious] Stopped after {self._tick_count} ticks")

    async def _tick(self, trigger: str):
        if self._tick_count > 120:
            self._tick_count = 0  # Reset yearly count to avoid overflow
        self._tick_count += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*40}")
        print(f"[Subconscious #{self._tick_count}] Triggered by: {trigger} at {ts}")
        print(f"{'='*40}")

        from skill_system.distillation import DistillationEngine
        from memory.extractor import EntityExtractor

        # Step 1: Distillation (gradual: NL→SOP→optimize→CODE, one step per request)
        distiller = DistillationEngine(self._neo4j, self._llm)
        await distiller.process_pending()
        pending = await self._get_pending_count()
        print(f"  [Distillation] Processed, remaining: {pending}")

        # Step 2: Entity extraction
        extractor = EntityExtractor(self._neo4j, self._llm)
        await extractor.extract_recent()
        entity_count = await self._get_entity_count()
        print(f"  [Extractor] Entities extracted, total L2 entities: {entity_count}")

        # Step 3: Belief revision — check contradictions
        from memory.belief import BeliefReviser
        reviser = BeliefReviser(self._neo4j)
        conflicts = await reviser.check_contradictions()
        if conflicts:
            print(f"  [Belief] Resolved {len(conflicts)} contradiction(s)")

        # Step 4: Lifecycle
        await self._lifecycle.evict_compressed_steps()
        print(f"  [Lifecycle] Evicted compressed steps")
        await self._lifecycle.decay_all()
        await self._lifecycle.forget_stale()
        stats = await self._lifecycle.get_stats()
        print(f"  [Lifecycle] Decay+forget done, stats: {stats}")

        # Step 5: Archive mining (every 12 ticks)
        if self._tick_count % 12 == 0:
            from memory.archive_miner import ArchiveMiner
            miner = ArchiveMiner(self._neo4j)
            patterns = await miner.mine()
            if patterns:
                print(f"  [ArchiveMiner] Recovered {len(patterns)} patterns: {patterns[:5]}")

        # Step 6: Autonomous exploration (every 120 ticks or idle trigger)
        if self._dispatcher and (self._tick_count % 120 == 0 or trigger == "idle"):
            from exploration.planner import ExplorationPlanner
            from exploration.executor import ExplorationExecutor
            from exploration.reflector import ExplorationReflector

            planner = ExplorationPlanner(self._neo4j)
            tasks = await planner.plan(max_tasks=1)
            if tasks:
                print(f"  [Exploration] Planning: {len(tasks)} task(s)")
                executor = ExplorationExecutor(self._neo4j, self._llm, self._dispatcher, self._config)
                for task in tasks[:1]:
                    label = task.get("name") or task.get("category", "?")
                    print(f"  [Exploration] Executing: {task['type']} — {label}")
                    result = await executor.execute(task, max_rounds=15)
                    reflector = ExplorationReflector(self._neo4j, self._llm)
                    await reflector.reflect(result)
                    stats = await reflector.get_exploration_stats()
                    print(f"  [Exploration] Done: {result['status']}, stats: {stats}")
            else:
                print(f"  [Exploration] No tasks to explore")

        print(f"{'='*40}\n")

    async def _get_pending_count(self) -> int:
        r = await self._neo4j.run(
            "MATCH (d:DistillationRequest {status: 'pending'}) RETURN count(d) AS c"
        )
        return r[0]["c"] if r else 0

    async def _get_entity_count(self) -> int:
        r = await self._neo4j.run("MATCH (e:Entity) RETURN count(e) AS c")
        return r[0]["c"] if r else 0
