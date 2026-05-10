"""Phase 1 integration tests — verifies tools, compression, context, and agent flow."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.config import Config, LLMConfig, Neo4jConfig
from agent.compression import CompressionPipeline, truncate_head_tail
from agent.context import ContextBuilder
from tools.dispatcher import ToolDispatcher
from tools.file_ops import FileReadTool, FileWriteTool, FilePatchTool
from tools.code_run import CodeRunTool
from tools.ask_user import AskUserTool
from tools.base import ToolCall
from memory.graph_models import (
    ContentBlock, Skill, EntityNode, ExecutionStep,
    AgentNode, UserNode, MetaPatternNode, SkillCategoryNode,
    Base64Source, URLSource,
)
from memory.index import L1Index
from memory.neo4j_client import Neo4jClient


PASS = 0
FAIL = 0

def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} -- {detail}")


async def test_1_file_tools():
    print("\n--- Test 1: File Operations ---")
    dispatcher = ToolDispatcher()
    dispatcher.register(FileReadTool())
    dispatcher.register(FileWriteTool())
    dispatcher.register(FilePatchTool())

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "test.txt"
        f.write_text("line1: hello\nline2: world\nline3: foo\nline4: bar\nline5: baz\n")

        r = await dispatcher.dispatch(ToolCall(id="c1", name="file_read",
            arguments={"path": str(f), "start": 2, "count": 2}))
        check("file_read range", r.success and "line3" in r.output, f"out={r.output[:60]}")

        r = await dispatcher.dispatch(ToolCall(id="c2", name="file_read",
            arguments={"path": str(f), "keyword": "bar"}))
        check("file_read keyword", r.success and "bar" in r.output, f"out={r.output[:60]}")

        r = await dispatcher.dispatch(ToolCall(id="c3", name="file_read",
            arguments={"path": "/nonexistent/file.txt"}))
        check("file_read missing", not r.success and "not found" in r.error.lower(), f"err={r.error}")

        new_f = Path(tmp) / "new.txt"
        r = await dispatcher.dispatch(ToolCall(id="c4", name="file_write",
            arguments={"path": str(new_f), "content": "hello world"}))
        check("file_write creates", r.success and new_f.read_text() == "hello world", f"out={r.output}")

        r = await dispatcher.dispatch(ToolCall(id="c5", name="file_patch",
            arguments={"path": str(f), "old_content": "line3: foo", "new_content": "line3: replaced"}))
        check("file_patch success", r.success and "applied" in r.output.lower(), f"out={r.output}")

        r = await dispatcher.dispatch(ToolCall(id="c6", name="file_patch",
            arguments={"path": str(f), "old_content": "nonexistent", "new_content": "x"}))
        check("file_patch no match", not r.success and "not found" in r.error.lower(), f"err={r.error}")

        f2 = Path(tmp) / "dup.txt"
        f2.write_text("dup\nmiddle\ndup\n")
        r = await dispatcher.dispatch(ToolCall(id="c7", name="file_patch",
            arguments={"path": str(f2), "old_content": "dup", "new_content": "x"}))
        check("file_patch multi match", not r.success and "2 locations" in r.error.lower(), f"err={r.error}")


async def test_2_code_run():
    print("\n--- Test 2: Code Execution ---")
    tmp = Path(".").resolve() / "workspace" / "test_code_run"
    tmp.mkdir(parents=True, exist_ok=True)
    tool = CodeRunTool(workspace_dir=str(tmp))

    r = await tool.execute(ToolCall(id="c1", name="code_run",
        arguments={"code": "print('hello from sandbox')"}))
    check("code_run prints", r.success and "hello from sandbox" in r.output, f"out={r.output[:60]}")

    r = await tool.execute(ToolCall(id="c2", name="code_run",
        arguments={"code": "raise ValueError('test error')"}))
    check("code_run error", not r.success and "ValueError" in r.output, f"out={r.output[:80]}")

    r = await tool.execute(ToolCall(id="c3", name="code_run",
        arguments={"code": "import time; time.sleep(3)", "timeout": 1}))
    check("code_run timeout", not r.success and "Timeout" in r.error, f"err={r.error}")


async def test_3_ask_user():
    print("\n--- Test 3: Ask User ---")
    tool = AskUserTool()
    r = await tool.execute(ToolCall(id="c1", name="ask_user",
        arguments={"question": "Which file?", "options": ["a.py", "b.py"]}))
    check("ask_user format", r.success and "[ASK_USER]" in r.output, f"out={r.output}")
    check("ask_user options", "a.py" in r.output and "b.py" in r.output, "")


async def test_4_compression():
    print("\n--- Test 4: Compression ---")
    pipeline = CompressionPipeline(context_budget_chars=90000)

    long_out = "A" * 15000
    truncated = pipeline.stage1_tool_output("code_run", long_out)
    check("stage1 truncates", len(truncated) < len(long_out), f"new_len={len(truncated)}")
    check("stage1 head preserved", truncated.startswith("A"), "")
    check("stage1 tail preserved", truncated.endswith("A"), "")

    memory_out = "B" * 15000
    full = pipeline.stage1_tool_output("memory_search", memory_out)
    check("stage1 memory_search kept full", len(full) == len(memory_out), "")

    long_msg = [{"role": "user", "content": "X" * 1000} for _ in range(20)]
    compressed = pipeline.stage2_compress_tags(long_msg, recent_exempt=10)
    check("stage2 compresses old", len(compressed[0]["content"]) < 1000, f"len={len(compressed[0]['content'])}")

    pipeline_small = CompressionPipeline(context_budget_chars=5000)
    many = [{"role": "user", "content": "x" * 300}] * 50
    evicted = pipeline_small.stage3_evict(many)
    check("stage3 reduces", len(evicted) < len(many), f"{len(many)}->{len(evicted)}")
    check("stage3 starts with user", evicted[0]["role"] == "user", f"role={evicted[0]['role']}")

    r = truncate_head_tail("START" + "X" * 5000 + "END", max_len=1000)
    check("head_tail start preserved", "START" in r, "")
    check("head_tail end preserved", "END" in r, "")


async def test_5_context():
    print("\n--- Test 5: Context Builder ---")
    dispatcher = ToolDispatcher()
    dispatcher.register(FileReadTool())
    dispatcher.register(AskUserTool())

    builder = ContextBuilder(dispatcher, agent_name="test-agent")
    prompt = builder.build_system_prompt(turn_number=5,
        recent_summaries="  [4] read\n  [5] found",
        key_info="Goal: test\nFindings: ok")

    checks = [
        ("meta-memory", "Meta-Memory" in prompt),
        ("core rules", "L1 First" in prompt),
        ("turn number", "Turn: 5" in prompt),
        ("summaries", "found" in prompt),
        ("key_info", "Goal: test" in prompt),
        ("tools listed", "file_read" in prompt and "ask_user" in prompt),
        ("agent name", "test-agent" in prompt),
    ]
    for name, cond in checks:
        check(f"context: {name}", cond, "")

    from llm.base import Message
    msgs = builder.build_messages(user_message="hello", history=[],
        turn_number=1, recent_summaries="(none)", key_info="(none)")
    check("build_messages system first", msgs[0].role == "system", "")
    check("build_messages user last", msgs[-1].role == "user" and msgs[-1].content == "hello", "")


async def test_6_graph_models():
    print("\n--- Test 6: Graph Models ---")

    valid_types = {"text", "thinking", "tool_use", "tool_result", "image", "audio", "video"}
    for t in valid_types:
        cb = ContentBlock(type=t)
        check(f"ContentBlock {t}", cb.type == t, "")

    tb = ContentBlock(type="text", text="Hello")
    check("TextBlock text", tb.text == "Hello", "")

    th = ContentBlock(type="thinking", thinking="analyze...")
    check("ThinkingBlock", th.thinking == "analyze...", "")

    tu = ContentBlock(type="tool_use", id="call_1", name="file_read", input={"path": "/x"})
    check("ToolUseBlock", tu.name == "file_read" and tu.input == {"path": "/x"}, "")

    tr = ContentBlock(type="tool_result", id="call_1", name="file_read", output="data")
    check("ToolResultBlock", tr.output == "data", "")

    img = ContentBlock(type="image", source=Base64Source(media_type="image/png", data="b64"))
    check("ImageBlock base64", img.source.media_type == "image/png", "")

    aud = ContentBlock(type="audio", source=URLSource(url="https://x.com/a.mp3"))
    check("AudioBlock url", aud.source.url == "https://x.com/a.mp3", "")

    step = ExecutionStep(id="msg_001", name="noesis", role="assistant",
        content=[ContentBlock(type="text", text="Done.")])
    check("ExecutionStep", step.id == "msg_001" and step.role == "assistant", "")

    entity = EntityNode(entity_id="e1", entity_type="Service", name="Neo4j",
        content="DB", properties={"host": "10.0.1.50", "port": 7687})
    check("EntityNode type", entity.entity_type == "Service", "")
    check("EntityNode props", entity.properties["host"] == "10.0.1.50", "")

    skill = Skill(skill_id="s1", name="Test", description="desc",
        category="test", dir="skills/test/s1/")
    check("SkillNode", skill.stage == "NL" and skill.description == "desc", "")

    agent = AgentNode(agent_id="a1", name="Alpha")
    check("AgentNode", agent.evolution_policy == "balanced", "")

    user = UserNode(user_id="u1", name="Alice")
    check("UserNode", user.user_id == "u1", "")

    pattern = MetaPatternNode(pattern_id="p1", name="Search", description="...")
    check("MetaPatternNode", pattern.pattern_id == "p1", "")

    cat = SkillCategoryNode(name="web_automation")
    check("SkillCategoryNode", cat.name == "web_automation", "")

    from memory.graph_models import DistillationRequestNode
    dr = DistillationRequestNode(session_id="s1", reason="subgoal_completed", summary="ok")
    check("DistillationRequestNode", dr.status == "pending", "")


async def test_7_neo4j_schema():
    print("\n--- Test 7: Neo4j Schema ---")
    try:
        config = Neo4jConfig()
        client = Neo4jClient(config)
        await client.init_schema()
        records = await client.run("SHOW CONSTRAINTS")
        check("constraints exist", len(records) >= 5, f"count={len(records)}")
        records = await client.run("SHOW INDEXES")
        btree = [r for r in records if r.get("type") != "FULLTEXT"]
        check("indexes exist", len(btree) >= 5, f"count={len(btree)}")
        await client.close()
    except Exception as e:
        check("neo4j connection", False, f"Error: {e}")


async def test_8_l1_index():
    print("\n--- Test 8: L1 Index ---")
    try:
        config = Neo4jConfig()
        client = Neo4jClient(config)
        idx = L1Index(client)

        await client.run("""MERGE (s:Skill {skill_id: 'idx-test'})
            SET s.name='IndexTest', s.category='test', s.stage='NL',
                s.version=1, s.activation=1.0, s.usage_count=5,
                s.dir='skills/test/idx-test/'""")

        results = await idx.search_skills(category="test")
        check("search by category", any(r["skill_id"] == "idx-test" for r in results), f"n={len(results)}")

        skill = await idx.get_skill("idx-test")
        check("get skill", skill is not None and skill["skill_id"] == "idx-test", "")

        await idx.update_activation("idx-test", 0.1)
        await client.run("MATCH (s:Skill {skill_id: 'idx-test'}) DETACH DELETE s")
        await client.close()
    except Exception as e:
        check("L1 index", False, f"Error: {e}")


async def test_9_memory_tools():
    print("\n--- Test 9: Memory Tools ---")
    try:
        config = Neo4jConfig()
        client = Neo4jClient(config)

        from tools.memory_search import MemorySearchTool
        from tools.checkpoint import UpdateWorkingCheckpointTool
        from tools.long_term_update import StartLongTermUpdateTool
        from tools.skill_manage import SkillManageTool

        ms = MemorySearchTool(client)
        s = ms.schema()
        check("memory_search schema", s.name == "memory_search", "")
        check("memory_search has rag", "rag" in str(s.parameters), "")

        r = await ms.execute(ToolCall(id="c1", name="memory_search",
            arguments={"mode": "route", "keyword": "xyz_nonexistent"}))
        check("route empty", r.success, f"out={r.output[:60]}")

        cp = UpdateWorkingCheckpointTool(client)
        r = await cp.execute(ToolCall(id="c2", name="update_working_checkpoint",
            arguments={"session_id": "tsess", "goal": "test"}))
        check("checkpoint", r.success and "updated" in r.output.lower(), f"out={r.output}")

        lt = StartLongTermUpdateTool(client)
        r = await lt.execute(ToolCall(id="c3", name="start_long_term_update",
            arguments={"session_id": "tsess", "reason": "reusable_pattern", "summary": "test"}))
        check("long_term_update", r.success and "queued" in r.output.lower(), f"out={r.output}")

        sm = SkillManageTool(client)
        r = await sm.execute(ToolCall(id="c4", name="skill_manage",
            arguments={"action": "register", "skill_id": "test-ms",
                       "name": "TMS", "category": "test", "dir": "skills/test/t/"}))
        check("skill_manage", r.success and "registered" in r.output.lower(), f"out={r.output}")

        await client.run("MATCH (s:Skill {skill_id: 'test-ms'}) DETACH DELETE s")
        await client.run("MATCH (s:Session {session_id: 'tsess'}) DETACH DELETE s")
        await client.run("MATCH (d:DistillationRequest) WHERE d.session_id='tsess' DETACH DELETE d")
        await client.close()
    except Exception as e:
        check("memory tools", False, f"Error: {e}")


async def test_10_tool_registry():
    print("\n--- Test 10: Tool Registry ---")
    from agent.engine import AgentEngine
    config = Config()
    engine = AgentEngine(config)
    names = engine.dispatcher.tool_names()
    required = [
        "file_read", "file_patch", "file_write", "code_run",
        "web_scan", "web_execute_js", "memory_search",
        "update_working_checkpoint", "start_long_term_update",
        "skill_manage", "subagent", "ask_user",
    ]
    for name in required:
        check(f"tool: {name}", name in names, f"available={sorted(names)}")
    check("total 12 tools", len(names) == 12, f"count={len(names)}")

    schemas = engine.dispatcher.get_schemas()
    for s in schemas:
        desc = s["function"]["description"]
        check(f"  desc: {s['function']['name']}", len(desc) > 10, f"desc={desc[:60]}")
    await engine.neo4j.close()


async def main():
    global PASS, FAIL
    print("=" * 50)
    print("  Noesis Phase 1 Integration Tests")
    print("=" * 50)

    await test_1_file_tools()
    await test_2_code_run()
    await test_3_ask_user()
    await test_4_compression()
    await test_5_context()
    await test_6_graph_models()
    await test_7_neo4j_schema()
    await test_8_l1_index()
    await test_9_memory_tools()
    await test_10_tool_registry()

    print("\n" + "=" * 50)
    print(f"  Results: {PASS} PASS, {FAIL} FAIL")
    print("=" * 50)
    return FAIL == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
