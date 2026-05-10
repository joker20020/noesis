"""Conscious loop — ReAct pattern + AgentScope-compatible Message model."""
import json, uuid
from pathlib import Path
from llm.base import LlmClient, Message, ContentBlock, ToolCall
from tools.dispatcher import ToolDispatcher
from tools.base import ToolCall as DispatchToolCall
from memory.neo4j_client import Neo4jClient
from memory.index import L1Index
from agent.context import ContextBuilder
from agent.compression import CompressionPipeline
from agent.config import Config

MAX_HISTORY_MSGS = 20


def _dict_to_message(d: dict) -> Message:
    """Convert a dict (from compression or DB) back to Message."""
    content = d.get("content", "")
    role = d.get("role", "user")
    if isinstance(content, str):
        try:
            blocks_raw = json.loads(content)
            blocks = [ContentBlock(**b) if isinstance(b, dict) else ContentBlock(type="text", text=str(b))
                      for b in blocks_raw]
            return Message(role=role, content=blocks)
        except (json.JSONDecodeError, TypeError):
            pass
        # Parse the text format: [think] ... / [tool_use: ...] / [result: ...]
        blocks = []
        for line in content.split("\n"):
            if line.startswith("[think] "):
                blocks.append(ContentBlock(type="thinking", thinking=line[8:]))
            elif line.startswith("[tool_use: "):
                # Extract name and input from "[tool_use: name({...})]"
                inner = line[11:-1]
                if "(" in inner:
                    name = inner[:inner.index("(")]
                    input_str = inner[inner.index("(")+1:inner.rindex(")")] if ")" in inner else "{}"
                    try: input_val = json.loads(input_str.replace("'", '"'))
                    except Exception: input_val = {}
                else:
                    name = inner; input_val = {}
                blocks.append(ContentBlock(type="tool_use", name=name, input=input_val))
            elif line.startswith("[result: "):
                blocks.append(ContentBlock(type="tool_result", output=line[9:]))
            elif line.strip():
                blocks.append(ContentBlock(type="text", text=line))
        return Message(role=role, content=blocks) if blocks else Message.text_msg(role, content)
    if isinstance(content, list):
        blocks = [ContentBlock(**b) if isinstance(b, dict) else b for b in content]
        return Message(role=role, content=blocks)
    return Message.text_msg(role, str(content))


def _msg_to_dict(m: Message) -> dict:
    """Serialize Message to dict — tool_use + tool_result paired to survive compression."""
    texts = []
    pending_tool = None  # tool_use waiting for its result
    for b in m.content:
        if b.type == "thinking":
            texts.append(f"[think] {b.thinking or ''}")
        elif b.type == "text":
            texts.append(b.text or "")
        elif b.type == "tool_use":
            pending_tool = f"[tool_use: {b.name}({b.input})]"
        elif b.type == "tool_result":
            if pending_tool:
                texts.append(f"{pending_tool}\n[result: {b.output or ''[:200]}]")
                pending_tool = None
            else:
                texts.append(f"[result: {b.output or ''[:200]}]")
    if pending_tool:
        texts.append(pending_tool)  # Unpaired tool_use (shouldn't happen)
    return {"role": m.role, "content": "\n".join(texts) or "(tool)"}


class ConsciousLoop:
    def __init__(self, llm_client: LlmClient, dispatcher: ToolDispatcher,
                 neo4j: Neo4jClient, config: Config,
                 session_id: str | None = None, workspace_dir: str | None = None):
        self._llm = llm_client
        self._dispatcher = dispatcher
        self._neo4j = neo4j
        self._config = config
        self._index = L1Index(neo4j)
        self._context_builder = ContextBuilder(dispatcher)
        self._compression = CompressionPipeline(context_budget_chars=config.context_budget_tokens * 3)
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self._workspace = Path(workspace_dir or config.workspace_dir)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._history: list[Message] = []
        self._turn_count = 0
        self._step_index = 0
        self._last_step_id: str | None = None
        self._last_20_summaries: list[str] = []
        self._history_summary = ""
        self._l1_skills = "(no skills registered yet)"
        self._aborted = False

    def abort(self):
        self._aborted = True

    async def run(self, user_input: str, max_rounds: int = 30,
                  history: list[dict] | None = None, on_event=None) -> str:
        is_ephemeral = self.session_id.startswith("explore_")

        if not is_ephemeral:
            records = await self._neo4j.run(
                """MERGE (s:Session {session_id: $sid})
                   ON CREATE SET s.type='main', s.status='running', s.created_at=datetime(), s.turn_count=0, s.key_info=''
                   ON MATCH  SET s.status='running'
                   RETURN coalesce(s.turn_count,0) AS turn_count""",
                {"sid": self.session_id})
            if records:
                self._turn_count = records[0].get("turn_count", 0)
            # Get latest step_index
            idx_rec = await self._neo4j.run(
                """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
                   MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
                   RETURN coalesce(max(step.step_index), 0) AS max_idx""",
                {"sid": self.session_id})
            self._step_index = idx_rec[0]["max_idx"] if idx_rec else 0

        await self._load_l1_skills()

        last_rec = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               WHERE NOT (step)-[:NEXT]->()
               RETURN step.id AS id ORDER BY step.step_index DESC LIMIT 1""",
            {"sid": self.session_id})
        if last_rec:
            self._last_step_id = last_rec[0].get("id")

        if not history and self._turn_count > 0 and not self._history:
            history = await self._load_history_from_db()
        if history:
            total = len(history)
            if total > MAX_HISTORY_MSGS:
                older = history[:total - MAX_HISTORY_MSGS]; 
                recent = history[total - MAX_HISTORY_MSGS:]
                self._history_summary = self._summarize_history([_msg_to_dict(m) for m in older])
                self._history.extend(recent)
            else:
                self._history.extend(history)
            raw = [_msg_to_dict(m) for m in self._history]
            if self._compression._char_count(raw) > self._compression.budget:
                self._history = [_dict_to_message(m) for m in self._compression.stage3_evict(raw)]

        self._aborted = False
        self._history.append(Message.text_msg("user", user_input))
        if not is_ephemeral:
            await self._log_user_step(user_input)


        for round_idx in range(max_rounds):
            if self._aborted:
                self._history.append(Message.text_msg("system", "[Interrupted]"))
                return "[Interrupted]"
            self._turn_count += 1

            if self._turn_count > 1 and self._turn_count % 5 == 0:
                raw = [_msg_to_dict(m) for m in self._history]
                compressed = self._compression.stage2_compress_tags(raw)
                self._history = [_dict_to_message(m) for m in compressed]

            total_s = len(self._last_20_summaries)
            start = max(0, total_s - 5)
            recent_text = "\n".join(f"  [{total_s - i}] {s}" for i, s in enumerate(reversed(self._last_20_summaries[start:total_s])))
            key_info = await self._get_key_info()

            if round_idx == 0:
                from memory.anticipatory import AnticipatoryRetrieval
                preload = await AnticipatoryRetrieval(self._neo4j).preload_hint(user_input, self.session_id)
                if preload:
                    key_info = preload + "\n" + key_info

            system = self._context_builder.build_system_prompt(
                self._turn_count, recent_text or "(none)", key_info,
                self._history_summary, self.session_id, self._l1_skills)
            messages = [Message.text_msg("system", system)]
            messages.extend(self._history)

            response = await self._llm.chat(messages, self._dispatcher.get_schemas())

            # Build round blocks for single-step DB save
            round_blocks: list[dict] = []

            # Thought — preserve original block types from API
            if response.content and response.tool_calls:
                self._history.append(Message(role="assistant", content=response.content))
                for b in response.content:
                    if b.type == "thinking":
                        round_blocks.append({"type": "thinking", "thinking": b.thinking or ""})
                    elif b.type == "text":
                        round_blocks.append({"type": "text", "text": b.text or ""})
                if on_event:
                    display = "".join(b.text or b.thinking or "" for b in response.content)
                    await on_event({"type": "message", "content": display})
                if not is_ephemeral and round_blocks:
                    await self._create_step("infocap", "assistant", round_blocks)

            # Task complete
            if not response.tool_calls:
                self._history.append(Message(role="assistant", content=response.content))
                for b in response.content:
                    if b.type == "thinking":
                        round_blocks.append({"type": "thinking", "thinking": b.thinking or ""})
                    elif b.type == "text":
                        round_blocks.append({"type": "text", "text": b.text or ""})
                if not is_ephemeral and round_blocks:
                    await self._create_step("infocap", "assistant", round_blocks)
                display = "".join(b.text or "" for b in response.content if b.type == "text") or "Task completed."
                if on_event:
                    await on_event({"type": "message", "content": display})
                if not is_ephemeral:
                    await self._finalize_session()
                return display

            # Action + Observation (all tool calls)
            for tc in response.tool_calls:
                if self._aborted:
                    return "[Interrupted]"

                result = await self._dispatcher.dispatch(DispatchToolCall(id=tc.id, name=tc.name, arguments=tc.arguments))
                truncated = self._compression.stage1_tool_output(tc.name, result.output)

                await self._create_step("infocap", "assistant", 
                                        [{"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}])
                await self._create_step("infocap", "system", 
                                        [{"type": "tool_result", "tool_call_id": tc.id, "name": tc.name, "output": truncated}])
                

                # Store tool_use + tool_result in ONE Message so they stay paired
                self._history.append(Message(role="assistant", content=[
                    ContentBlock(type="tool_use", id=tc.id, name=tc.name, input=tc.arguments)]))
                self._history.append(Message(role="system", content=[
                    ContentBlock(type="tool_result", tool_call_id=tc.id, name=tc.name, output=truncated)]))

                if on_event:
                    await on_event({"type": "tool_result", "name": tc.name, "content": truncated})

            raw = [_msg_to_dict(m) for m in self._history]
            if self._compression._char_count(raw) > self._compression.budget:
                self._history = [_dict_to_message(m) for m in self._compression.stage3_evict(raw)]
            text = ""
            if response.content:
                text = "\n".join(b.text or "" for b in response.content)
            summary = text[:100] if response.content else f"Round {self._turn_count}"
            self._last_20_summaries.append(summary)
            if len(self._last_20_summaries) > 20:
                self._last_20_summaries = self._last_20_summaries[-20:]

            await self._neo4j.run(
                "MATCH (s:Session {session_id: $sid}) SET s.turn_count = $tc",
                {"sid": self.session_id, "tc": self._turn_count})

        if not is_ephemeral:
            await self._finalize_session()
        return "Max rounds reached."

    def _summarize_history(self, older):
        if not older: return ""
        user = [m for m in older if m.get("role") == "user"]
        return f"[Earlier: {len(user)} user msgs, {len(older)-len(user)} assistant]"

    async def _load_history_from_db(self) -> list[Message]:
        records = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               RETURN DISTINCT step ORDER BY step.step_index""",
            {"sid": self.session_id})
        msgs: list[Message] = []
        for r in records:
            step = r["step"]; 
            role = step.get("role", "assistant")
            content = step.get("content", "")
            if isinstance(content, str):
                try:
                    blocks = json.loads(content)
                    msgs.append(Message(role=role, content=[
                        ContentBlock(**b) if isinstance(b, dict) else ContentBlock(type="text", text=str(b))
                        for b in blocks]))
                except Exception:
                    msgs.append(Message.text_msg(role, str(content)[:500]))
        return msgs

    async def _load_l1_skills(self):
        skills = await self._index.search(top_k=30)
        if not skills:
            self._l1_skills = "(no skills registered yet — use skill_manage to create one)"; return
        lines = [f"{len(skills)} skills available:"]
        for s in skills:
            lines.append(f"  - {s.skill_id} [{s.stage}] v{s.version} used:{s.usage_count} — {s.name}")
        self._l1_skills = "\n".join(lines)

    async def _get_key_info(self) -> str:
        records = await self._neo4j.run(
            "MATCH (s:Session {session_id: $sid}) RETURN coalesce(s.key_info,'') AS key_info",
            {"sid": self.session_id})
        if records and records[0].get("key_info"):
            return records[0]["key_info"]
        if self._last_20_summaries:
            return "Recent: " + "; ".join(self._last_20_summaries[-3:])
        return "(no key info yet)"

    async def _finalize_session(self):
        await self._neo4j.run(
            "MATCH (s:Session {session_id: $sid}) SET s.status = 'completed'",
            {"sid": self.session_id})

    async def _create_step(self, name, role, blocks):
        import shortuuid
        self._step_index += 1
        sid = f"msg_{shortuuid.uuid()[:10]}"
        content_json = json.dumps(blocks, ensure_ascii=False)
        idx = self._step_index
        turn = self._turn_count
        if self._last_step_id is None:
            await self._neo4j.run(
                """MATCH (s:Session {session_id: $sid})
                   CREATE (s)-[:HAS_STEP]->(:ExecutionStep {
                     id:$id, name:$name, role:$role, step_index:$idx, turn:$turn,
                     content:$content, timestamp:datetime(), invocation_id:null})""",
                {"sid": self.session_id, "id": sid, "name": name, "role": role,
                 "idx": idx, "turn": turn, "content": content_json})
        else:
            await self._neo4j.run(
                """MATCH (prev:ExecutionStep {id:$pid})
                   CREATE (prev)-[:NEXT]->(:ExecutionStep {
                     id:$id, name:$name, role:$role, step_index:$idx, turn:$turn,
                     content:$content, timestamp:datetime(), invocation_id:null})""",
                {"pid": self._last_step_id, "id": sid, "name": name, "role": role,
                 "idx": idx, "turn": turn, "content": content_json})
        self._last_step_id = sid
        return sid

    async def _log_user_step(self, text):
        await self._create_step("user", "user", [{"type": "text", "text": text}])
