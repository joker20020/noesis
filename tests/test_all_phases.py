"""Comprehensive verification of all phases."""
import asyncio, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.config import Config
from agent.engine import AgentEngine
from llm.base import LlmClient, LlmResponse, Message

PASS = FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS: {name}")
    else: FAIL += 1; print(f"  FAIL: {name} -- {detail}")


class _FakeLLM(LlmClient):
    def __init__(self, content: str):
        self.content = content
        self.calls = 0

    async def chat(self, messages, tools=None):
        self.calls += 1
        return LlmResponse(content=self.content)


async def verify_phase1():
    print("\n" + "=" * 50)
    print("  PHASE 1 — Core Agent")
    print("=" * 50)

    # File tools
    from tools.dispatcher import ToolDispatcher
    from tools.file_ops import FileReadTool, FileWriteTool, FilePatchTool
    from tools.code_run import CodeRunTool
    from tools.ask_user import AskUserTool
    from tools.base import ToolCall
    from agent.compression import CompressionPipeline, truncate_head_tail
    from agent.context import ContextBuilder
    from memory.graph_models import ContentBlock, Skill, EntityNode, ExecutionStep, Base64Source

    # Tools
    with Path("./workspace/test_verify").resolve() as tmp:
        tmp.mkdir(parents=True, exist_ok=True)
        f = tmp / "t.txt"
        f.write_text("line1\na\nline2\nb\nline3\nc\n")
        d = ToolDispatcher()
        d.register(FileReadTool()); d.register(FileWriteTool()); d.register(FilePatchTool())
        r = await d.dispatch(ToolCall(id="c1", name="file_read", arguments={"path": str(f), "start": 2, "count": 2}))
        check("file ops: read range", r.success and "line2" in r.output)

    r = await CodeRunTool("./workspace/test_verify").execute(ToolCall(id="c1", name="code_run", arguments={"command": "echo verify_ok"}))
    check("code run: shell", r.success and "verify_ok" in r.output)

    r = await AskUserTool().execute(ToolCall(id="c1", name="ask_user", arguments={"question": "test"}))
    check("ask user: format", r.success and "[ASK_USER]" in r.output)

    # Compression
    p = CompressionPipeline(90000)
    out = p.stage1_tool_output("code_run", "X" * 15000)
    check("compression: stage1", len(out) < 15000)
    evicted = CompressionPipeline(2000).stage3_evict([{"role": "user", "content": "x" * 500}] * 50)
    check("compression: stage3", len(evicted) < 50)
    check("head-tail: preserves", "H" in truncate_head_tail("H" + "X" * 5000 + "T", 1000) and "T" in truncate_head_tail("H" + "X" * 5000 + "T", 1000))

    # Context
    d.register(FileReadTool())
    b = ContextBuilder(d)
    prompt = b.build_system_prompt(turn_number=1, session_id="sess_x", l1_skills="2 skills:\n  - a/b [NL] v1 — Test")
    check("context: meta-memory", "Meta-Memory" in prompt)
    check("context: session_id", "sess_x" in prompt)
    check("context: L1 injected", "a/b" in prompt)

    # Graph models
    for t in ("text", "thinking", "tool_use", "tool_result", "image", "audio", "video"):
        check(f"graph: ContentBlock.{t}", ContentBlock(type=t).type == t)
    check("graph: Skill", Skill(skill_id="s1", name="S", dir="d").skill_id == "s1")
    check("graph: Entity", EntityNode(entity_id="e1", entity_type="T", name="N", content="C").properties.get("p") is None)
    check("graph: ExecutionStep", ExecutionStep(id="m1", name="x", role="user", content=[ContentBlock(type="text", text="hi")]).id == "m1")


async def verify_phase2(engine):
    print("\n" + "=" * 50)
    print("  PHASE 2 — Skill System + Memory")
    print("=" * 50)

    from skill_system.registry import SkillRegistry
    from skill_system.template import generate_skill_md
    from memory.entities import EntityManager
    from memory.lifecycle import MemoryLifecycle

    reg = SkillRegistry(engine.neo4j, engine.config.skills_dir)

    r = await reg.register("vfy-skill", "test", "Verification skill")
    check("skill: register", r["skill_id"] == "test/vfy-skill")
    p = Path(engine.config.skills_dir) / "test" / "vfy-skill"
    check("skill: SKILL.md exists", (p / "SKILL.md").exists())
    check("skill: scripts dir", (p / "scripts").is_dir())

    md_nl = generate_skill_md("v", "d", "c", stage="NL")
    md_sop = generate_skill_md("v", "d", "c", stage="SOP")
    md_code = generate_skill_md("v", "d", "c", stage="CODE", scripts=["main.py"])
    check("template: NL", "NL" in md_nl)
    check("template: SOP", "SOP" in md_sop)
    check("template: CODE", "CODE" in md_code and "main.py" in md_code)

    em = EntityManager(engine.neo4j)
    await em.create("ent_vfy", "Config", "Test Config", "Test entity", {"k": "v"})
    results = await em.search(keyword="Test")
    check("entity: create+search", len(results) > 0 and results[0]["entity_type"] == "Config")

    lc = MemoryLifecycle(engine.neo4j)
    stats = await lc.get_stats()
    check("lifecycle: stats", "skills" in stats and "entities" in stats and "patterns" in stats)

    # Cleanup
    await engine.neo4j.run("MATCH (s:Skill {skill_id: 'test/vfy-skill'}) DETACH DELETE s")
    await engine.neo4j.run("MATCH (e:Entity {entity_id: 'ent_vfy'}) DETACH DELETE e")
    await engine.neo4j.run("MATCH (c:SkillCategory {name: 'test'}) DETACH DELETE c")
    shutil.rmtree(p, ignore_errors=True)


async def verify_phase3(engine, llm):
    print("\n" + "=" * 50)
    print("  PHASE 3 — Self-Evolution")
    print("=" * 50)

    # Extractor
    from memory.extractor import EntityExtractor
    ex = EntityExtractor(engine.neo4j, llm)
    await engine.neo4j.run("""MERGE (d:DistillationRequest {session_id: 'vfy-ext'})
        SET d.reason = 'subgoal_completed', d.summary = 'Found PostgreSQL on 10.0.1.50 managed by Alice',
            d.status = 'completed', d.processed_at = datetime()""")
    await ex.extract_recent(lookback_minutes=1440)
    r = await engine.neo4j.run("MATCH (e:Entity {source: 'llm_extracted'}) RETURN count(e) AS c")
    check("extractor: LLM entities", r[0]["c"] > 0, f"count={r[0]['c']}")

    # Distillation
    from skill_system.distillation import DistillationEngine
    await engine.neo4j.run("""MERGE (d:DistillationRequest {session_id: 'vfy-dist'})
        SET d.reason = 'reusable_pattern', d.summary = 'Standard deployment procedure using docker compose',
            d.status = 'pending', d.created_at = datetime()""")
    de = DistillationEngine(engine.neo4j, llm)
    await de.process_pending()
    r = await engine.neo4j.run("MATCH (d:DistillationRequest {session_id: 'vfy-dist'}) RETURN d.status AS s")
    check("distillation: processed", r[0]["s"] == "completed")

    # Scoring
    from skill_system.scorer import SkillScorer
    scorer = SkillScorer(engine.neo4j)
    scores = await scorer.score_all()
    check("scorer: produces results", isinstance(scores, list))
    if scores:
        check("scorer: has dimensions", "dimensions" in scores[0])
        old_w = dict(scorer.weights)
        await scorer.adapt_weights({"score": 9.0, "dimensions": {"B": 8.0, "D": 2.0, "U": 1.0, "I": 0.0}}, 0)
        check("scorer: weight adaptation", scorer.weights != old_w)

    # Optimizer
    from skill_system.optimizer import SopOptimizer
    opt = SopOptimizer(engine.neo4j, llm)
    result = await opt.optimize("test/vfy-opt")  # expect None (no data)
    check("optimizer: handles empty", result is None)

    # Compiler
    from skill_system.compiler import SopCompiler
    comp = SopCompiler(engine.neo4j, llm, skills_dir=engine.config.skills_dir)
    r = await comp.compile_if_ready("nonexistent/skill")
    check("compiler: handles missing", r is None)

    # Lifecycle
    from memory.lifecycle import MemoryLifecycle
    lc = MemoryLifecycle(engine.neo4j)
    await lc.decay_all()
    await lc.consolidate_entity("ent_vfy_entity", 0.2)  # should not crash if missing
    check("lifecycle: decay+consolidate", True)

    # Cleanup
    await engine.neo4j.run("MATCH (d:DistillationRequest) WHERE d.session_id STARTS WITH 'vfy-' DETACH DELETE d")
    await engine.neo4j.run("MATCH (e:Entity {source: 'llm_extracted'}) DETACH DELETE e")


async def verify_phase4(engine):
    print("\n" + "=" * 50)
    print("  PHASE 4 — Autonomous Exploration")
    print("=" * 50)

    from exploration.planner import ExplorationPlanner
    from exploration.reflector import ExplorationReflector

    planner = ExplorationPlanner(engine.neo4j)
    tasks = await planner.plan(max_tasks=5)
    check("planner: returns tasks", isinstance(tasks, list))
    if tasks:
        types = [t["type"] for t in tasks]
        check("planner: explore type", "explore" in types, str(types))
        check("planner: has prompts", all(len(t["prompt"]) > 20 for t in tasks))
        print(f"    Generated {len(tasks)} tasks: {types}")

    gaps = await planner.get_gap_analysis()
    check("planner: gap analysis", "missing" in gaps and "existing" in gaps)
    print(f"    Existing categories: {len(gaps['existing'])}")
    print(f"    Missing categories: {len(gaps['missing'])}")

    reflector = ExplorationReflector(engine.neo4j)
    stats = await reflector.get_exploration_stats()
    check("reflector: stats", isinstance(stats, dict))
    await reflector._adapt_weights()
    check("reflector: weight adaptation", True)

    check("subconscious: exists", engine._subconscious is not None)
    check("subconscious: has dispatcher", engine._subconscious._dispatcher is not None)
    check("subconscious: has LLM", engine._subconscious._llm is not None)


async def verify_tool_registry(engine):
    print("\n" + "=" * 50)
    print("  TOOL REGISTRY")
    print("=" * 50)

    expected = [
        ("file_read", "Phase 1"), ("file_patch", "Phase 1"), ("file_write", "Phase 1"),
        ("code_run", "Phase 1"), ("web_scan", "Phase 1"), ("web_execute_js", "Phase 1"),
        ("memory_search", "Phase 1"), ("update_working_checkpoint", "Phase 1"),
        ("start_long_term_update", "Phase 1"), ("skill_manage", "Phase 1+2"),
        ("ask_user", "Phase 1"), ("subagent", "Phase 1"),
        ("entity_manage", "Phase 2"), ("meta_pattern", "Phase 2"),
    ]
    names = engine.dispatcher.tool_names()
    for name, phase in expected:
        check(f"tool: {name} ({phase})", name in names)
    check("tool count: 14", len(names) == 14, f"actual={len(names)}")

    for s in engine.dispatcher.get_schemas():
        desc = s["function"]["description"]
        check(f"  desc >10: {s['function']['name']}", len(desc) > 10, desc[:50])


async def main():
    global PASS, FAIL
    print("=" * 50)
    print("  Noesis All-Phase Verification")
    print("=" * 50)

    # Phase 1 (no engine needed)
    await verify_phase1()

    # Engine init
    config = Config()
    engine = AgentEngine(config)
    await engine.init()

    # Fake LLM for Phase 3 tests
    llm = _FakeLLM(json.dumps({
        "entities": [{"entity_id": "ent_db", "entity_type": "Service", "name": "PostgreSQL",
                       "content": "DB", "properties": {"host": "10.0.1.50"}}],
        "relations": [{"from": "ent_db", "type": "MANAGED_BY", "to": "ent_db"}],
    }))

    await verify_phase2(engine)
    await verify_phase3(engine, llm)
    await verify_phase4(engine)
    await verify_tool_registry(engine)

    await engine.close()

    print("\n" + "=" * 50)
    print(f"  TOTAL: {PASS} PASS, {FAIL} FAIL")
    print("=" * 50)
    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
