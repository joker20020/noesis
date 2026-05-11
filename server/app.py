import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from agent.config import Config
from agent.engine import AgentEngine


def _parse_content(content):
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return []
    return content or []


_engine: AgentEngine | None = None
_adapter_tasks: list[asyncio.Task] = []

FIXED_SESSION = "noesis"


async def _start_adapters():
    """Start platform adapters based on config. All share session 'noesis'."""
    cfg = _engine.config.platform
    tasks = []

    # WeChat — direct iLink API (GA-compatible)
    if cfg.wechat_enabled:
        from adapters.wechat import WeChatAdapter
        wx = WeChatAdapter(_engine)
        tasks.append(asyncio.create_task(wx.start(), name="wechat"))
        print(f"[Server] WeChat: iLink API")

    # QQ — Tencent official botpy SDK
    if cfg.qq_enabled:
        from adapters.qq import QQAdapter
        qq = QQAdapter(_engine, app_id=cfg.qq_app_id, app_secret=cfg.qq_app_secret, allowed_users=cfg.qq_allowed_users)
        tasks.append(asyncio.create_task(qq.start(), name="qq"))
        print(f"[Server] QQ: botpy SDK")

    # Telegram
    if cfg.telegram_enabled:
        from adapters.telegram import TelegramAdapter
        allowed = {int(u) for u in cfg.telegram_allowed_users.split(",") if u.strip()} if cfg.telegram_allowed_users else set()
        tg = TelegramAdapter(_engine, token=cfg.telegram_token, allowed_users=allowed)
        tasks.append(asyncio.create_task(tg.start(), name="telegram"))
        print(f"[Server] Telegram: started (allowed: {len(allowed)} users)")

    # Discord — discord.py
    if cfg.discord_enabled:
        from adapters.discord import DiscordAdapter
        channels = cfg.discord_channels
        dc = DiscordAdapter(_engine, token=cfg.discord_token, channel_ids=channels)
        tasks.append(asyncio.create_task(dc.start(), name="discord"))
        print(f"[Server] Discord: started (channels: {channels or 'all'})")

    # Feishu — lark-oapi SDK
    if cfg.feishu_enabled:
        from adapters.feishu import FeishuAdapter
        fs = FeishuAdapter(_engine, app_id=cfg.feishu_app_id, app_secret=cfg.feishu_app_secret)
        tasks.append(asyncio.create_task(fs.start(), name="feishu"))
        print(f"[Server] Feishu: started")

    if not tasks:
        print("[Server] No platform adapters enabled (configure .env to enable)")
    return tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _adapter_tasks
    config = Config()
    # Diagnostic: print all platform adapter states
    p = config.platform
    print(f"[Server] Adapter config — WeChat:{p.wechat_enabled} QQ:{p.qq_enabled} "
          f"Telegram:{p.telegram_enabled} Discord:{p.discord_enabled} Feishu:{p.feishu_enabled}")
    _engine = AgentEngine(config)
    try:
        await _engine.init()
    except Exception as e:
        print(f"[WARN] Neo4j schema init failed (may not be running): {e}")

    try:
        _adapter_tasks = await _start_adapters()
    except Exception as e:
        print(f"[Server] Adapter startup error: {e}")

    yield

    # Graceful shutdown
    try:
        for task in _adapter_tasks:
            task.cancel()
        await asyncio.gather(*_adapter_tasks, return_exceptions=True)
    except Exception:
        pass
    try:
        await _engine.close()
    except Exception:
        pass


app = FastAPI(title="Noesis", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/history")
async def get_history():
    """Get history for the fixed session."""
    records = await _engine.neo4j.run(
        """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
           MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
           RETURN DISTINCT step ORDER BY step.step_index""",
        {"sid": FIXED_SESSION},
    )
    messages = []
    for r in records:
        step = r["step"]
        for block in _parse_content(step.get("content", [])):
            if block["type"] == "thinking":
                text = block.get("thinking", block.get("text", ""))
                if text:
                    messages.append({"role": "assistant", "content": text})
            elif block["type"] == "text":
                messages.append({"role": step.get("role", "assistant"), "content": block.get("text", "")})
            elif block["type"] == "tool_result":
                messages.append({"role": "system", "content": f"[{block.get('name', 'tool')}]\n{block.get('output', '')}"})
    return {"session_id": FIXED_SESSION, "messages": messages}


@app.get("/api/skills")
async def list_skills():
    records = await _engine.neo4j.run(
        """MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED'
           RETURN s.skill_id AS id, s.name AS name, s.description AS desc,
                  s.category AS cat, s.stage AS stage, s.version AS ver,
                  coalesce(s.usage_count, 0) AS used, s.dir AS dir
           ORDER BY s.category, s.name"""
    )
    return [dict(r) for r in records]


@app.post("/api/skills")
async def create_skill(data: dict):
    from skill_system.registry import SkillRegistry
    reg = SkillRegistry(_engine.neo4j, _engine.config.skills_dir)
    result = await reg.register(
        name=data.get("name", "untitled"),
        category=data.get("category", "general"),
        description=data.get("description", ""),
        stage=data.get("stage", "NL"),
        create_files=True,
    )
    return {"status": "created", **result}


@app.get("/api/skills/{skill_id:path}")
async def get_skill_detail(skill_id: str):
    """Get skill detail with SKILL.md content and evolution chain."""
    from pathlib import Path
    records = await _engine.neo4j.run(
        "MATCH (s:Skill {skill_id: $sid}) RETURN s", {"sid": skill_id})
    if not records:
        return {"error": "not found"}
    skill = dict(records[0]["s"])

    # Load SKILL.md content
    md_path = Path(skill.get("dir", "")) / "SKILL.md"
    skill["skill_md"] = md_path.read_text(encoding="utf-8") if md_path.exists() else "(no SKILL.md)"

    # Get related entities
    entity_records = await _engine.neo4j.run(
        """MATCH (s:Skill {skill_id: $sid})-[:REFERENCES]->(e:Entity)
           RETURN e LIMIT 20""", {"sid": skill_id})
    skill["entities"] = [dict(r["e"]) for r in entity_records]

    # Get relationships
    rel_records = await _engine.neo4j.run(
        """MATCH (s:Skill {skill_id: $sid})-[r]->(related)
           WHERE related:Skill OR related:Entity OR related:MetaPattern
           RETURN type(r) AS rel, labels(related) AS labels, related LIMIT 20""",
        {"sid": skill_id})
    skill["relations"] = [{"type": r["rel"], "target": dict(r["related"]),
                           "labels": r["labels"]} for r in rel_records]

    return skill


@app.get("/api/memory/graph")
async def get_memory_graph(keyword: str = "", limit: int = 30):
    """Return nodes and edges for visualization."""
    nodes = []
    edges = []

    if keyword:
        entity_query = """CALL db.index.fulltext.queryNodes('entity_search', $kw)
            YIELD node AS e, score WHERE score > 0.2 RETURN e LIMIT $lim"""
    else:
        entity_query = "MATCH (e:Entity) RETURN e ORDER BY coalesce(e.activation, 0) DESC LIMIT $lim"

    records = await _engine.neo4j.run(entity_query, {"kw": keyword, "lim": limit})
    entity_ids = set()
    for r in records:
        e = dict(r["e"])
        eid = e["entity_id"]
        entity_ids.add(eid)
        nodes.append({"id": eid, "label": e.get("name", eid),
                      "type": e.get("entity_type", "Entity"), "group": "entity"})

    # Get relationships between these entities
    if entity_ids:
        rel_records = await _engine.neo4j.run(
            """MATCH (a:Entity)-[r]->(b:Entity)
               WHERE a.entity_id IN $ids AND b.entity_id IN $ids
               RETURN a.entity_id AS from, type(r) AS rel, b.entity_id AS to LIMIT 100""",
            {"ids": list(entity_ids)})
        for r in rel_records:
            edges.append({"from": r["from"], "to": r["to"], "label": r["rel"]})

    return {"nodes": nodes, "edges": edges}


@app.delete("/api/skills/{skill_id:path}")
async def delete_skill(skill_id: str):
    from skill_system.registry import SkillRegistry
    import shutil
    from pathlib import Path
    reg = SkillRegistry(_engine.neo4j, _engine.config.skills_dir)
    skill = await reg.get(skill_id)
    if skill:
        # Remove filesystem
        skill_dir = Path(skill.get("dir", ""))
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        # Remove Neo4j node + relationships
        await _engine.neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) DETACH DELETE s", {"sid": skill_id})
        # Update category count
        await _engine.neo4j.run(
            """MATCH (c:SkillCategory) WHERE NOT (c)<-[:BELONGS_TO]-(:Skill) DETACH DELETE c""")
    return {"status": "deleted"}


@app.post("/api/abort")
async def abort():
    _engine.abort()
    return {"status": "aborted"}


@app.delete("/api/session")
async def clear_session():
    await _engine.restart_session()
    return {"status": "cleared"}


@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    from server.ws import ChatHandler
    handler = ChatHandler(_engine)  # type: ignore
    await handler.handle(ws)
