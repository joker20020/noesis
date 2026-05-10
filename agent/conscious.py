"""Conscious loop — ReAct pattern: Thought → Action → Observation → repeat."""
import json
import uuid
from pathlib import Path
from llm.base import LlmClient, Message
from tools.dispatcher import ToolDispatcher
from tools.base import ToolCall as DispatchToolCall
from memory.neo4j_client import Neo4jClient
from memory.index import L1Index
from agent.context import ContextBuilder
from agent.compression import CompressionPipeline
from agent.config import Config

MAX_HISTORY_MSGS = 20


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

        # ── Session init ──
        if not is_ephemeral:
            records = await self._neo4j.run(
                """MERGE (s:Session {session_id: $sid})
                   ON CREATE SET s.type='main', s.status='running', s.created_at=datetime(), s.turn_count=0, s.key_info=''
                   ON MATCH  SET s.status='running'
                   RETURN coalesce(s.turn_count,0) AS turn_count""",
                {"sid": self.session_id})
            if records:
                self._turn_count = records[0].get("turn_count", 0)

        await self._load_l1_skills()

        # Find last step for NEXT chaining
        last_rec = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               WHERE NOT (step)-[:NEXT]->()
               RETURN step.id AS id ORDER BY step.step_index DESC LIMIT 1""",
            {"sid": self.session_id})
        if last_rec:
            self._last_step_id = last_rec[0].get("id")

        # Auto-load history from Neo4j on first run when session existed before
        if not history and self._turn_count > 0 and not self._history:
            history = await self._load_history_from_db()
        if history:
            total_loaded = len(history)
            if total_loaded > MAX_HISTORY_MSGS:
                older = history[:total_loaded - MAX_HISTORY_MSGS]
                recent = history[total_loaded - MAX_HISTORY_MSGS:]
                self._history_summary = self._summarize_history(older)
                for h in recent:
                    self._history.append(Message(role=h.get("role", "assistant"), content=h["content"]))
            else:
                for h in history:
                    self._history.append(Message(role=h.get("role", "assistant"), content=h["content"]))
            raw = [{"role": m.role, "content": m.content} for m in self._history]
            if self._compression._char_count(raw) > self._compression.budget:
                self._history = [Message(**m) for m in self._compression.stage3_evict(raw)]

        # ── ReAct Loop: one tool per round ──
        self._aborted = False
        # Add user message to history (only once)
        self._history.append(Message(role="user", content=user_input))
        if not is_ephemeral:
            await self._log_user_step(user_input)

        for round_idx in range(max_rounds):
            if self._aborted:
                self._history.append(Message(role="assistant", content="[Interrupted]"))
                return "[Interrupted]"
            self._turn_count += 1

            # Stage 2: compress every 5 rounds
            if self._turn_count > 1 and self._turn_count % 5 == 0:
                raw = [{"role": m.role, "content": m.content} for m in self._history]
                compressed = self._compression.stage2_compress_tags(raw)
                self._history = [Message(**m) for m in compressed]

            # Stage 4: working memory anchors
            total = len(self._last_20_summaries)
            start = max(0, total - 5)
            recent_text = "\n".join(
                f"  [{total - i}] {s}"
                for i, s in enumerate(reversed(self._last_20_summaries[start:total])))
            key_info = await self._get_key_info()

            # Anticipatory preload on first round
            if round_idx == 0:
                from memory.anticipatory import AnticipatoryRetrieval
                ar = AnticipatoryRetrieval(self._neo4j)
                preload = await ar.preload_hint(user_input, self.session_id)
                if preload:
                    key_info = preload + "\n" + key_info

            # Build messages: system prompt + full history (user already in history)
            system = self._context_builder.build_system_prompt(
                self._turn_count, recent_text or "(none)", key_info,
                self._history_summary, self.session_id, self._l1_skills)
            messages = [Message(role="system", content=system)]
            messages.extend(self._history)

            # LLM call
            tool_schemas = self._dispatcher.get_schemas()
            response = await self._llm.chat(messages, tool_schemas)

            # ── ReAct: Thought (text before tool calls) ──
            if response.content and response.tool_calls:
                if not is_ephemeral:
                    await self._log_thinking_step(response.content)
                if on_event:
                    await on_event({"type": "message", "content": response.content})
                # Record thinking in history for context
                self._history.append(Message(role="assistant", content=response.content))

            # ── No tool calls: task complete ──
            if not response.tool_calls:
                final = response.content or "Task completed."
                self._history.append(Message(role="assistant", content=final))
                if not is_ephemeral:
                    await self._log_text_step(final)
                if on_event:
                    await on_event({"type": "message", "content": final})
                if not is_ephemeral:
                    await self._finalize_session()
                return final

            # ── ReAct: Action + Observation (ONE tool at a time) ──
            tc = response.tool_calls[0]  # Execute only the first tool
            if self._aborted:
                return "[Interrupted]"

            result = await self._dispatcher.dispatch(
                DispatchToolCall(id=tc.id, name=tc.name, arguments=tc.arguments))
            truncated = self._compression.stage1_tool_output(tc.name, result.output)

            # Log to L0
            if not is_ephemeral:
                await self._log_tool_result(tc.name, truncated)

            # Record tool call + result in history
            self._history.append(Message(
                role="assistant",
                content=f"[Tool: {tc.name}({tc.arguments})]"))
            self._history.append(Message(
                role="tool", content=truncated,
                tool_call_id=tc.id, name=tc.name))

            if on_event:
                await on_event({"type": "tool_result", "name": tc.name, "content": truncated})

            # Stage 3: eviction check after adding tool results
            raw = [{"role": m.role, "content": m.content} for m in self._history]
            if self._compression._char_count(raw) > self._compression.budget:
                self._history = [Message(**m) for m in self._compression.stage3_evict(raw)]

            # Stage 4 summary
            summary = response.content[:100] if response.content else f"Round {self._turn_count}"
            self._last_20_summaries.append(summary)
            if len(self._last_20_summaries) > 20:
                self._last_20_summaries = self._last_20_summaries[-20:]

            await self._neo4j.run(
                "MATCH (s:Session {session_id: $sid}) SET s.turn_count = $tc",
                {"sid": self.session_id, "tc": self._turn_count})

        if not is_ephemeral:
            await self._finalize_session()
        return "Max rounds reached."

    # ── helpers ──
    def _summarize_history(self, older: list[dict]) -> str:
        if not older: return ""
        user_msgs = [m for m in older if m.get("role") == "user"]
        lines = [f"[Earlier: {len(user_msgs)} user msgs, {len(older)-len(user_msgs)} assistant]"]
        if user_msgs: lines.append(f"  First: {user_msgs[0]['content'][:100]}")
        return "\n".join(lines)

    async def _load_history_from_db(self) -> list[dict]:
        records = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               RETURN DISTINCT step ORDER BY step.step_index""",
            {"sid": self.session_id})
        msgs = []
        for r in records:
            step = r["step"]; content = step.get("content", "")
            if isinstance(content, str):
                try:
                    for block in json.loads(content):
                        if block["type"] == "text":
                            msgs.append({"role": step.get("role","assistant"), "content": block.get("text","")})
                except Exception: pass
        return msgs

    async def _load_l1_skills(self):
        skills = await self._index.search(top_k=30)
        if not skills:
            self._l1_skills = "(no skills registered yet — use skill_manage to create one)"
            return
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

    # ── Step logging ──
    async def _create_step(self, name, role, blocks):
        import shortuuid
        sid = f"msg_{shortuuid.uuid()[:10]}"
        if self._last_step_id is None:
            await self._neo4j.run(
                """MATCH (s:Session {session_id: $sid})
                   CREATE (s)-[:HAS_STEP]->(:ExecutionStep {
                     id:$id, name:$name, role:$role, step_index:$idx, turn:$turn,
                     content:$content, timestamp:datetime(), invocation_id:null})""",
                {"sid": self.session_id, "id": sid, "name": name, "role": role,
                 "idx": self._turn_count, "turn": self._turn_count,
                 "content": json.dumps(blocks)})
        else:
            await self._neo4j.run(
                """MATCH (prev:ExecutionStep {id:$pid})
                   CREATE (prev)-[:NEXT]->(:ExecutionStep {
                     id:$id, name:$name, role:$role, step_index:$idx, turn:$turn,
                     content:$content, timestamp:datetime(), invocation_id:null})""",
                {"pid": self._last_step_id, "id": sid, "name": name, "role": role,
                 "idx": self._turn_count, "turn": self._turn_count,
                 "content": json.dumps(blocks)})
        self._last_step_id = sid
        return sid

    async def _log_user_step(self, text):
        await self._create_step("user", "user", [{"type": "text", "text": text}])
    async def _log_thinking_step(self, thinking):
        return await self._create_step("infocap", "assistant", [{"type": "thinking", "thinking": thinking}])
    async def _log_text_step(self, text, role="assistant"):
        return await self._create_step("infocap" if role == "assistant" else role, role, [{"type": "text", "text": text}])
    async def _log_tool_result(self, tool_name, output):
        return await self._create_step(tool_name, "system", [{"type": "tool_result", "name": tool_name, "output": output}])
