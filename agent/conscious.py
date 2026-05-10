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

MAX_HISTORY_MSGS = 20  # Max recent messages to load in full; older ones get summarized


class ConsciousLoop:
    def __init__(
        self,
        llm_client: LlmClient,
        dispatcher: ToolDispatcher,
        neo4j: Neo4jClient,
        config: Config,
        session_id: str | None = None,
        workspace_dir: str | None = None,
    ):
        self._llm = llm_client
        self._dispatcher = dispatcher
        self._neo4j = neo4j
        self._config = config
        self._index = L1Index(neo4j)
        self._context_builder = ContextBuilder(dispatcher)
        self._compression = CompressionPipeline(
            context_budget_chars=config.context_budget_tokens * 3
        )
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self._workspace = Path(workspace_dir or config.workspace_dir)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._history: list[Message] = []
        self._turn_count = 0
        self._last_step_id: str | None = None  # For [:NEXT] chaining
        self._last_20_summaries: list[str] = []
        self._history_summary = ""
        self._l1_skills = "(no skills registered yet)"
        self._aborted = False

    def abort(self):
        self._aborted = True

    async def run(self, user_input: str, max_rounds: int = 30, history: list[dict] | None = None,
                  on_event=None) -> str:
        # Only persist non-exploration sessions
        is_ephemeral = self.session_id.startswith("explore_")
        if not is_ephemeral:
            records = await self._neo4j.run(
                """MERGE (s:Session {session_id: $sid})
                   ON CREATE SET s.type = 'main', s.status = 'running', s.created_at = datetime(), s.turn_count = 0, s.key_info = ''
                   ON MATCH  SET s.status = 'running'
                   RETURN coalesce(s.turn_count, 0) AS turn_count""",
                {"sid": self.session_id},
            )
            if records:
                self._turn_count = records[0].get("turn_count", 0)

        # Load L1 skill index for always-on awareness
        await self._load_l1_skills()

        # Find last step for [:NEXT] chaining on resume
        last_rec = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               WHERE NOT (step)-[:NEXT]->()
               RETURN step.id AS id ORDER BY step.step_index DESC LIMIT 1""",
            {"sid": self.session_id},
        )
        if last_rec:
            self._last_step_id = last_rec[0].get("id")

        # Auto-load history from Neo4j on first run when session existed before
        if not history and self._turn_count > 0 and not self._history:
            history = await self._load_history_from_db()
        # Load history from Neo4j on resume, with truncation for older messages
        if history:
            total_loaded = len(history)
            if total_loaded > MAX_HISTORY_MSGS:
                # Keep only the last MAX_HISTORY_MSGS in full; summarize the rest
                older = history[:total_loaded - MAX_HISTORY_MSGS]
                recent = history[total_loaded - MAX_HISTORY_MSGS:]
                self._history_summary = self._summarize_history(older)
                for h in recent:
                    role = h.get("role", "assistant")
                    self._history.append(Message(role=role, content=h["content"]))
            else:
                for h in history:
                    role = h.get("role", "assistant")
                    self._history.append(Message(role=role, content=h["content"]))

            # Immediately evict if loaded history overflows budget
            raw = [{"role": m.role, "content": m.content} for m in self._history]
            if self._compression._char_count(raw) > self._compression.budget:
                self._history = [Message(**m) for m in self._compression.stage3_evict(raw)]

        self._aborted = False
        for round_idx in range(max_rounds):
            if self._aborted:
                self._history.append(Message(role="assistant", content="[Interrupted]"))
                return "[Interrupted]"
            self._turn_count += 1

            # Stage 2: compress old tags every 5 rounds
            if self._turn_count > 1 and self._turn_count % 5 == 0:
                raw = [{"role": m.role, "content": m.content} for m in self._history]
                compressed = self._compression.stage2_compress_tags(raw)
                self._history = [Message(**m) for m in compressed]

            total = len(self._last_20_summaries)
            start = max(0, total - 5)
            recent_text = "\n".join(
                f"  [{total - i}] {s}"
                for i, s in enumerate(reversed(self._last_20_summaries[start:total]))
            )
            key_info = await self._get_key_info()

            # Anticipatory preload (Phase 5): hint relevant memories to agent
            if round_idx == 0:
                from memory.anticipatory import AnticipatoryRetrieval
                ar = AnticipatoryRetrieval(self._neo4j)
                preload = await ar.preload_hint(user_input, self.session_id)
                if preload:
                    key_info = preload + "\n" + key_info

            current_input = user_input if round_idx == 0 else "(continue)"
            messages = self._context_builder.build_messages(
                user_message=current_input,
                history=self._history,
                turn_number=self._turn_count,
                recent_summaries=recent_text or "(none)",
                key_info=key_info,
                history_summary=self._history_summary,
                session_id=self.session_id,
                l1_skills=self._l1_skills,
            )
            if round_idx == 0:
                self._history.append(Message(role="user", content=user_input))
                if not is_ephemeral:
                    await self._log_user_step(user_input)

            tool_schemas = self._dispatcher.get_schemas()
            response = await self._llm.chat(messages, tool_schemas)

            # Log reasoning before tool calls as thinking block
            if response.content and response.tool_calls:
                if not is_ephemeral:
                    step_id = await self._log_thinking_step(response.content)
                if on_event:
                    await on_event({"type": "message", "content": response.content, "id": step_id if not is_ephemeral else None})

            # No tool calls: task is complete
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

            for tc in response.tool_calls:
                if self._aborted:
                    return "[Interrupted]"
                result = await self._dispatcher.dispatch(
                    DispatchToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
                )
                tool_output = result.output or result.error or "(empty)"
                truncated = self._compression.stage1_tool_output(tc.name, tool_output)
                if not is_ephemeral:
                    step_id = await self._log_tool_result(tc.name, truncated)
                else:
                    step_id = ""
                if on_event:
                    await on_event({"type": "tool_result", "name": tc.name, "content": truncated, "id": step_id})

                self._history.append(Message(
                    role="assistant", content=f"Tool: {tc.name}({tc.arguments})",
                ))
                self._history.append(Message(
                    role="tool", content=truncated, tool_call_id=tc.id, name=tc.name,
                ))

            # Stage 3: evict oldest messages if over budget
            raw = [{"role": m.role, "content": m.content} for m in self._history]
            if self._compression._char_count(raw) > self._compression.budget:
                self._history = [Message(**m) for m in self._compression.stage3_evict(raw)]

            summary = response.content[:100] if response.content else f"Round {self._turn_count}"
            self._last_20_summaries.append(summary)
            if len(self._last_20_summaries) > 20:
                self._last_20_summaries = self._last_20_summaries[-20:]

            await self._neo4j.run(
                "MATCH (s:Session {session_id: $sid}) SET s.turn_count = $tc",
                {"sid": self.session_id, "tc": self._turn_count},
            )

        if not is_ephemeral:
            await self._finalize_session()
        return "Max rounds reached."

    def _summarize_history(self, older: list[dict]) -> str:
        """Create a brief summary of older history for context."""
        if not older:
            return ""
        user_msgs = [m for m in older if m.get("role") == "user"]
        assistant_msgs = [m for m in older if m.get("role") == "assistant"]
        lines = ["[Earlier conversation summary]"]
        lines.append(f"  {len(user_msgs)} user messages, {len(assistant_msgs)} assistant responses")
        if user_msgs:
            lines.append(f"  First user message: {user_msgs[0]['content'][:100]}")
        if assistant_msgs:
            lines.append(f"  Last assistant response: {assistant_msgs[-1]['content'][:150]}")
        return "\n".join(lines)

    async def _create_step(self, name: str, role: str, content_blocks: list[dict]) -> str:
        """Create an ExecutionStep node. First step gets [:HAS_STEP] from Session,
        subsequent steps get [:NEXT] from the previous step."""
        import shortuuid
        step_id = f"msg_{shortuuid.uuid()[:10]}"
        if self._last_step_id is None:
            # First step: Session -> HAS_STEP -> Step
            await self._neo4j.run(
                """MATCH (s:Session {session_id: $sid})
                   CREATE (s)-[:HAS_STEP]->(step:ExecutionStep {
                     id: $id, name: $name, role: $role,
                     step_index: $idx, turn: $turn,
                     content: $content,
                     timestamp: datetime(), invocation_id: null
                   })""",
                {"sid": self.session_id, "id": step_id, "name": name,
                 "role": role, "idx": self._turn_count, "turn": self._turn_count,
                 "content": json.dumps(content_blocks)},
            )
        else:
            # Subsequent: Prev -> NEXT -> Step
            await self._neo4j.run(
                """MATCH (prev:ExecutionStep {id: $prev_id})
                   CREATE (prev)-[:NEXT]->(step:ExecutionStep {
                     id: $id, name: $name, role: $role,
                     step_index: $idx, turn: $turn,
                     content: $content,
                     timestamp: datetime(), invocation_id: null
                   })""",
                {"prev_id": self._last_step_id, "id": step_id, "name": name,
                 "role": role, "idx": self._turn_count, "turn": self._turn_count,
                 "content": json.dumps(content_blocks)},
            )
        self._last_step_id = step_id
        return step_id

    async def _log_user_step(self, text: str):
        await self._create_step("user", "user", [{"type": "text", "text": text}])

    async def _log_thinking_step(self, thinking: str) -> str:
        return await self._create_step("infocap", "assistant", [
            {"type": "thinking", "thinking": thinking},
        ])

    async def _log_text_step(self, text: str, role: str = "assistant") -> str:
        return await self._create_step(
            "infocap" if role == "assistant" else role, role,
            [{"type": "text", "text": text}],
        )

    async def _log_tool_result(self, tool_name: str, output: str) -> str:
        return await self._create_step(tool_name, "system", [
            {"type": "tool_result", "name": tool_name, "output": output},
        ])

    async def _load_history_from_db(self) -> list[dict]:
        """Load recent ExecutionSteps as message history."""
        import json
        records = await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
               MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
               RETURN DISTINCT step ORDER BY step.step_index LIMIT 50""",
            {"sid": self.session_id},
        )
        msgs = []
        for r in records:
            step = r["step"]
            content = step.get("content", "")
            if isinstance(content, str):
                try:
                    blocks = json.loads(content)
                except Exception:
                    continue
                for block in blocks:
                    if block["type"] == "text":
                        msgs.append({"role": step.get("role", "assistant"), "content": block.get("text", "")})
        return msgs

    async def _load_l1_skills(self):
        """Load available Skills for L1 always-on awareness via L1Index."""
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
            "MATCH (s:Session {session_id: $sid}) RETURN coalesce(s.key_info, '') AS key_info",
            {"sid": self.session_id},
        )
        if records and records[0].get("key_info"):
            return records[0]["key_info"]
        # Auto-generate fallback from recent summaries
        if self._last_20_summaries:
            return "Recent: " + "; ".join(self._last_20_summaries[-3:])
        return "(no key info yet)"

    async def _finalize_session(self):
        await self._neo4j.run(
            "MATCH (s:Session {session_id: $sid}) SET s.status = 'completed'",
            {"sid": self.session_id},
        )
