"""Phase 2 comprehensive test — verifies ALL Phase 1 + 2 features work correctly."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = FAIL = 0

def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} -- {detail}")


# ====== Phase 1: File Tools ======
async def test_file_ops():
    print("\n[1] File Operations")
    from tools.dispatcher import ToolDispatcher
    from tools.file_ops import FileReadTool, FileWriteTool, FilePatchTool
    from tools.base import ToolCall

    d = ToolDispatcher()
    d.register(FileReadTool()); d.register(FileWriteTool()); d.register(FilePatchTool())

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("line1: a\nline2: b\nline3: c\nline4: d\nline5: e\n")

        r = await d.dispatch(ToolCall(id="c1", name="file_read", arguments={"path": str(f), "start": 2, "count": 2}))
        check("file_read range", r.success and "line3" in r.output)

        r = await d.dispatch(ToolCall(id="c2", name="file_read", arguments={"path": str(f), "keyword": "d"}))
        check("file_read keyword", r.success and "line4" in r.output)

        r = await d.dispatch(ToolCall(id="c3", name="file_read", arguments={"path": "/nonexistent"}))
        check("file_read missing", not r.success)

        r = await d.dispatch(ToolCall(id="c4", name="file_write", arguments={"path": str(Path(tmp)/"n.txt"), "content": "data"}))
        check("file_write", r.success and (Path(tmp)/"n.txt").read_text() == "data")

        r = await d.dispatch(ToolCall(id="c5", name="file_patch", arguments={"path": str(f), "old_content": "line3: c", "new_content": "line3: X"}))
        check("file_patch success", r.success and "X" in f.read_text())

        r = await d.dispatch(ToolCall(id="c6", name="file_patch", arguments={"path": str(f), "old_content": "noexist", "new_content": "x"}))
        check("file_patch no match", not r.success)

        (Path(tmp)/"dup.txt").write_text("dup\nmid\ndup\n")
        r = await d.dispatch(ToolCall(id="c7", name="file_patch", arguments={"path": str(Path(tmp)/"dup.txt"), "old_content": "dup", "new_content": "x"}))
        check("file_patch multi match", not r.success)


# ====== Phase 1: Code Run ======
async def test_code_run():
    print("\n[2] Code Run")
    from tools.code_run import CodeRunTool
    from tools.base import ToolCall

    tool = CodeRunTool(workspace_dir="./workspace/test_cr")
    r = await tool.execute(ToolCall(id="c1", name="code_run", arguments={"command": "echo hello_test_123"}))
    check("code_run echo", r.success and "hello_test_123" in r.output, f"out={r.output[:60]}")

    r = await tool.execute(ToolCall(id="c2", name="code_run", arguments={"command": "python -c \"print('py_out_456')\""}))
    check("code_run python", r.success and "py_out_456" in r.output, f"out={r.output[:60]}")

    r = await tool.execute(ToolCall(id="c3", name="code_run", arguments={"command": "exit 1"}))
    check("code_run fail", not r.success, f"err={r.error}")


# ====== Phase 1: Ask User ======
async def test_ask_user():
    print("\n[3] Ask User")
    from tools.ask_user import AskUserTool
    from tools.base import ToolCall
    tool = AskUserTool()
    r = await tool.execute(ToolCall(id="c1", name="ask_user", arguments={"question": "Which?", "options": ["a", "b"]}))
    check("ask_user format", r.success and "[ASK_USER]" in r.output and "a" in r.output)


# ====== Phase 1: Compression ======
async def test_compression():
    print("\n[4] Compression")
    from agent.compression import CompressionPipeline, truncate_head_tail

    p = CompressionPipeline(context_budget_chars=90000)

    out = p.stage1_tool_output("code_run", "X" * 15000)
    check("stage1 truncates long output", len(out) < 15000)

    out = p.stage1_tool_output("memory_search", "Y" * 15000)
    check("stage1 keeps memory_search", len(out) == 15000)

    msgs = [{"role": "user", "content": "Z" * 1000} for _ in range(20)]
    compressed = p.stage2_compress_tags(msgs, recent_exempt=10)
    check("stage2 compresses old", len(compressed[0]["content"]) < 1000)

    p2 = CompressionPipeline(context_budget_chars=2000)
    many = [{"role": "user", "content": "w" * 500}] * 50
    evicted = p2.stage3_evict(many)
    check("stage3 reduces", len(evicted) < 50)
    check("stage3 starts with user", evicted[0]["role"] == "user")

    r = truncate_head_tail("HEAD" + "X" * 5000 + "TAIL", max_len=1000)
    check("head_tail preserves HEAD", "HEAD" in r)
    check("head_tail preserves TAIL", "TAIL" in r)


# ====== Phase 1: Context Builder ======
async def test_context():
    print("\n[5] Context Builder")
    from agent.context import ContextBuilder
    from tools.dispatcher import ToolDispatcher
    from tools.file_ops import FileReadTool
    from tools.ask_user import AskUserTool
    from llm.base import Message

    d = ToolDispatcher(); d.register(FileReadTool()); d.register(AskUserTool())
    b = ContextBuilder(d, agent_name="test")

    prompt = b.build_system_prompt(turn_number=3, recent_summaries="[2] done",
        key_info="Goal: test", session_id="sess_123")
    for tag in ["Meta-Memory", "L1 Always-On", "Turn: 3", "test", "sess_123"]:
        check(f"prompt has '{tag}'", tag in prompt)

    msgs = b.build_messages("hello", [], turn_number=1)
    check("build_messages system first", msgs[0].role == "system")
    check("build_messages user last", msgs[-1].content == "hello")


# ====== Phase 1: Graph Models ======
async def test_graph_models():
    print("\n[6] Graph Models")
    from memory.graph_models import (
        ContentBlock, Skill, EntityNode, ExecutionStep,
        AgentNode, UserNode, MetaPatternNode, SkillCategoryNode,
        DistillationRequestNode, Base64Source, URLSource,
    )

    for t in ("text", "thinking", "tool_use", "tool_result", "image", "audio", "video"):
        check(f"ContentBlock {t}", ContentBlock(type=t).type == t)

    check("TextBlock", ContentBlock(type="text", text="hi").text == "hi")
    check("ThinkingBlock", ContentBlock(type="thinking", thinking="hmm").thinking == "hmm")
    check("ToolUseBlock", ContentBlock(type="tool_use", id="c1", name="f", input={"x":1}).name == "f")
    check("ToolResultBlock", ContentBlock(type="tool_result", output="ok").output == "ok")
    check("ImageBlock", ContentBlock(type="image", source=Base64Source(media_type="image/png")).source.media_type == "image/png")
    check("AudioBlock", ContentBlock(type="audio", source=URLSource(url="http://x")).source.url == "http://x")

    step = ExecutionStep(id="m1", name="infocap", role="assistant",
        content=[ContentBlock(type="text", text="done")])
    check("ExecutionStep", step.id == "m1" and step.role == "assistant")

    e = EntityNode(entity_id="e1", entity_type="Service", name="DB", content="...", properties={"p":7687})
    check("EntityNode", e.entity_type == "Service")

    s = Skill(skill_id="s1", name="S", description="D", category="c", dir="d")
    check("SkillNode", s.stage == "NL")

    a = AgentNode(agent_id="a1", name="A"); check("AgentNode", a.role == "default")
    u = UserNode(user_id="u1", name="U"); check("UserNode", u.user_id == "u1")
    mp = MetaPatternNode(pattern_id="p1", name="P", description="D"); check("MetaPatternNode", mp.pattern_id == "p1")
    sc = SkillCategoryNode(name="C"); check("SkillCategoryNode", sc.name == "C")
    dr = DistillationRequestNode(session_id="s1", reason="r", summary="s"); check("DistillationRequestNode", dr.status == "pending")


# ====== Phase 1+2: Tool Registry ======
async def test_tool_registry():
    print("\n[7] Tool Registry (14 tools)")
    from agent.config import Config
    from agent.engine import AgentEngine
    engine = AgentEngine(Config())
    names = engine.dispatcher.tool_names()
    expected = ["file_read", "file_patch", "file_write", "code_run", "web_scan", "web_execute_js",
                "memory_search", "update_working_checkpoint", "start_long_term_update",
                "skill_manage", "entity_manage", "meta_pattern", "subagent", "ask_user"]
    for t in expected:
        check(f"tool: {t}", t in names)
    check("total 14", len(names) == 14)

    for s in engine.dispatcher.get_schemas():
        d = s["function"]["description"]
        check(f"desc: {s['function']['name']}", len(d) > 10, d[:50])
    await engine.neo4j.close()


# ====== Phase 2: Skill System ======
async def test_skill_system():
    print("\n[8] Skill System (Registry + Template)")
    from agent.config import Config
    from agent.engine import AgentEngine
    from skill_system.registry import SkillRegistry
    from skill_system.template import generate_skill_md
    from pathlib import Path

    # Template
    for stage in ("NL", "SOP", "CODE"):
        md = generate_skill_md("test", "desc", "cat", stage=stage)
        check(f"template stage={stage}", f'stage: "{stage}"' in md)

    code_md = generate_skill_md("test", "desc", "cat", stage="CODE", scripts=["main.py", "fetch.py"])
    check("template CODE has scripts", "main.py" in code_md and "fetch.py" in code_md)

    # Registry
    config = Config()
    engine = AgentEngine(config)
    await engine.init()
    reg = SkillRegistry(engine.neo4j, config.skills_dir)

    r = await reg.register("phase2-test", "test", "A test skill")
    check("register", r["skill_id"] == "test/phase2-test")

    p = Path(config.skills_dir) / "test" / "phase2-test"
    check("SKILL.md exists", (p / "SKILL.md").exists())
    check("scripts/ exists", (p / "scripts").is_dir())
    check("references/ exists", (p / "references").is_dir())
    check("checkpoints/ exists", (p / "checkpoints").is_dir())

    skill = await reg.get("test/phase2-test")
    check("get skill", skill is not None and skill["stage"] == "NL")

    sop_content = generate_skill_md("phase2-test", "Updated SOP", "test", stage="SOP")
    await reg.update_stage("test/phase2-test", "SOP", content=sop_content)
    skill = await reg.get("test/phase2-test")
    check("evolve to SOP", skill["stage"] == "SOP")
    check("SKILL.md updated with SOP", "SOP" in (p / "SKILL.md").read_text())

    await reg.record_usage("test/phase2-test", True)
    skill = await reg.get("test/phase2-test")
    check("usage count", skill["usage_count"] == 1)
    check("activation boosted", skill["activation"] > 1.0)

    cats = await reg.list_categories()
    check("categories", any(c["name"] == "test" for c in cats))

    # Cleanup
    import shutil
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    await engine.neo4j.run("MATCH (s:Skill {skill_id: 'test/phase2-test'}) DETACH DELETE s")
    await engine.neo4j.run("MATCH (c:SkillCategory {name: 'test'}) DETACH DELETE c")
    await engine.close()


# ====== L1 Index ======
async def test_l1_index():
    print("\n[9] L1 Index")
    from memory.neo4j_client import Neo4jClient
    from memory.index import L1Index
    from agent.config import Neo4jConfig

    client = Neo4jClient(Neo4jConfig())
    idx = L1Index(client)

    await client.run("""MERGE (s:Skill {skill_id: 'l1-test'})
        SET s.name='L1Test', s.category='test', s.stage='NL', s.version=1,
            s.activation=1.0, s.usage_count=3, s.dir='skills/test/l1-test/'""")

    results = await idx.search(category="test")
    check("search", any(s.skill_id == "l1-test" for s in results))
    skill = await idx.get("l1-test")
    check("get", skill is not None)
    await idx.update_activation("l1-test", 0.2)

    await client.run("MATCH (s:Skill {skill_id: 'l1-test'}) DETACH DELETE s")
    await client.close()


# ====== L2 Entity CRUD ======
async def test_entity_crud():
    print("\n[10] L2 Entity CRUD")
    from memory.neo4j_client import Neo4jClient
    from memory.entities import EntityManager
    from agent.config import Neo4jConfig

    client = Neo4jClient(Neo4jConfig())
    mgr = EntityManager(client)

    await mgr.create("ent_a", "Person", "Alice", "Engineer", {"email": "a@x.com"})
    await mgr.create("ent_b", "Service", "DB", "Database", {"port": 5432})
    await mgr.link("ent_a", "MANAGES", "ent_b")

    results = await mgr.search(keyword="Alice")
    check("search by keyword", len(results) >= 1)
    check("props parsed", isinstance(results[0].get("properties"), dict))

    results = await mgr.search(entity_type="Service")
    check("search by type", len(results) >= 1)

    await mgr.update_confidence("ent_a", 0.1)

    await client.run("MATCH (e:Entity) WHERE e.entity_id IN ['ent_a','ent_b'] DETACH DELETE e")
    await client.close()


# ====== L4 MetaPattern ======
async def test_meta_pattern():
    print("\n[11] L4 MetaPattern")
    from memory.neo4j_client import Neo4jClient
    from memory.meta_pattern import MetaPatternManager
    from agent.config import Neo4jConfig

    client = Neo4jClient(Neo4jConfig())
    mgr = MetaPatternManager(client)

    # Create skills for extraction
    for sid, name, desc in [
        ("test/pat-s1", "Web Scraper", "Scrapes web pages using Playwright and extracts structured data"),
        ("test/pat-s2", "API Fetcher", "Fetches API data using HTTP and extracts JSON fields"),
    ]:
        await client.run(f"""MERGE (s:Skill {{skill_id: '{sid}'}})
            SET s.name='{name}', s.description='{desc}', s.category='test',
                s.stage='CODE', s.version=1, s.activation=1, s.dir='skills/test/{sid.split('/')[-1]}/'""")

    patterns = await mgr.extract_from_skills(category="test")
    check("extract finds patterns", len(patterns) > 0, f"found {len(patterns)}")

    await mgr.create("pat_manual", "Test Pattern", "A manually created pattern",
        abstract_steps=["Step 1", "Step 2"],
        source_skills=["test/pat-s1", "test/pat-s2"])

    results = await mgr.search(keyword="Test")
    check("search finds pattern", len(results) > 0)

    await mgr.apply_pattern("pat_manual")

    await client.run("MATCH (s:Skill) WHERE s.skill_id STARTS WITH 'test/' DETACH DELETE s")
    await client.run("MATCH (p:MetaPattern {pattern_id: 'pat_manual'}) DETACH DELETE p")
    await client.run("MATCH (c:SkillCategory {name: 'test'}) DETACH DELETE c")
    await client.close()


# ====== Memory Lifecycle ======
async def test_lifecycle():
    print("\n[12] Memory Lifecycle")
    from memory.neo4j_client import Neo4jClient
    from memory.lifecycle import MemoryLifecycle
    from agent.config import Neo4jConfig

    client = Neo4jClient(Neo4jConfig())
    lc = MemoryLifecycle(client)

    await client.run("""MERGE (s:Skill {skill_id: 'lifecycle-test'})
        SET s.name='LC', s.category='test', s.stage='NL', s.version=1,
            s.activation=0.3, s.dir='skills/test/lc/', s.created_at=datetime() - duration({days: 30})""")

    await lc.decay_all(days_threshold=7, rate=0.5)
    await lc.consolidate_skill("lifecycle-test", boost=0.5)

    stats = await lc.get_stats()
    check("lifecycle stats", stats["skills"] > 0, str(stats))

    await client.run("MATCH (s:Skill {skill_id: 'lifecycle-test'}) DETACH DELETE s")
    await client.run("MATCH (c:SkillCategory {name: 'test'}) DETACH DELETE c")
    await client.close()


# ====== Memory Search (Neo4j-dependent) ======
async def test_memory_search_modes():
    print("\n[13] Memory Search Modes")
    from memory.neo4j_client import Neo4jClient
    from tools.memory_search import MemorySearchTool
    from tools.checkpoint import UpdateWorkingCheckpointTool
    from tools.long_term_update import StartLongTermUpdateTool
    from tools.skill_manage import SkillManageTool
    from tools.base import ToolCall
    from agent.config import Neo4jConfig

    client = Neo4jClient(Neo4jConfig())

    ms = MemorySearchTool(client)
    r = await ms.execute(ToolCall(id="c1", name="memory_search", arguments={"mode": "rag", "keyword": "xyz_nonexist_999"}))
    check("rag empty", r.success)
    r = await ms.execute(ToolCall(id="c2", name="memory_search", arguments={"mode": "pattern", "keyword": "xyz_nonexist_999"}))
    check("pattern empty", r.success)

    r = await ms.execute(ToolCall(id="c2", name="memory_search", arguments={"mode": "rag", "keyword": "test database port", "strategy": "local"}))
    check("rag local", r.success, r.output[:80])

    r = await ms.execute(ToolCall(id="c3", name="memory_search", arguments={"mode": "rag", "keyword": "test", "strategy": "global"}))
    check("rag global", r.success)

    cp = UpdateWorkingCheckpointTool(client)
    r = await cp.execute(ToolCall(id="c4", name="update_working_checkpoint", arguments={"session_id": "tsess", "goal": "test", "findings": "ok"}))
    check("checkpoint writes", r.success)

    lt = StartLongTermUpdateTool(client)
    r = await lt.execute(ToolCall(id="c5", name="start_long_term_update", arguments={"session_id": "tsess", "reason": "reusable_pattern", "summary": "test"}))
    check("distillation queued", r.success)

    sm = SkillManageTool(client)
    r = await sm.execute(ToolCall(id="c6", name="skill_manage", arguments={"action": "register", "skill_id": "tmp-s", "name": "T", "category": "t", "dir": "skills/t/t/"}))
    check("skill_manage register", r.success and "registered" in r.output.lower())
    r = await sm.execute(ToolCall(id="c7", name="skill_manage", arguments={"action": "deprecate", "skill_id": "tmp-s"}))
    check("skill_manage deprecate", r.success)

    await client.run("MATCH (s:Skill {skill_id: 'tmp-s'}) DETACH DELETE s")
    await client.run("MATCH (s:Session {session_id: 'tsess'}) DETACH DELETE s")
    await client.run("MATCH (d:DistillationRequest) WHERE d.session_id='tsess' DETACH DELETE d")
    await client.close()


# ====== Neo4j Schema ======
async def test_schema():
    print("\n[14] Neo4j Schema")
    from memory.neo4j_client import Neo4jClient
    from agent.config import Neo4jConfig
    client = Neo4jClient(Neo4jConfig())
    await client.init_schema()
    r = await client.run("SHOW CONSTRAINTS")
    check("constraints exist", len(r) >= 5, f"count={len(r)}")
    r = await client.run("SHOW INDEXES")
    check("indexes exist", len(r) >= 8, f"count={len(r)}")
    await client.close()


# ====== MAIN ======
async def main():
    global PASS, FAIL
    print("=" * 50)
    print("  Phase 1+2 Comprehensive Test")
    print("=" * 50)

    await test_file_ops()
    await test_code_run()
    await test_ask_user()
    await test_compression()
    await test_context()
    await test_graph_models()
    await test_tool_registry()
    await test_skill_system()
    await test_l1_index()
    await test_entity_crud()
    await test_meta_pattern()
    await test_lifecycle()
    await test_memory_search_modes()
    await test_schema()

    print("\n" + "=" * 50)
    print(f"  Results: {PASS} PASS, {FAIL} FAIL")
    print("=" * 50)
    return FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
