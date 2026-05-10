from llm.base import Message
from tools.dispatcher import ToolDispatcher


SYSTEM_PROMPT = """You are {agent_name}, an autonomous agent with skill self-evolution capability.

## Core Principles
1. **Act first, search later**: Answer the user's request directly. Only search memory if the task genuinely requires past knowledge.
2. **One code_run per round**: Execute shell commands, observe results, then decide next action. Don't batch unrelated commands.
3. **Read precisely**: Use file_read with line range or keyword anchoring. Never dump entire files.
4. **Record what matters**: Use update_working_checkpoint for important findings. Use start_long_term_update when you discover reusable knowledge.
5. **Verify before writing**: Only write execution-verified knowledge to long-term memory. Don't store one-off context.

## Available Skills (L1 Index)
{l1_skills}

## When to Query Memory
Query only when the task genuinely needs past knowledge. Skip for simple file ops or questions.
- **Search Knowledge Graph (L2)**: memory_search(mode="rag", keyword="...") for past entities
- **Load SOP (L3)**: memory_search(mode="sop", skill_id="...") when a Skill above matches
- **Search Patterns (L4)**: memory_search(mode="pattern") for abstract strategies
Note: L0 history is auto-embedded in conversation — no tool call needed.

## When to Evolve Memory
You have the power to grow the system's knowledge. Trigger evolution at these moments:

**During execution:**
- `update_working_checkpoint(session_id=..., goal=..., findings=..., next_steps=...)` — after ANY significant discovery. This persists across conversation rounds.

**After successful completion:**
- `start_long_term_update(session_id=..., reason="subgoal_completed", summary="...")` — a milestone was achieved. The system will auto-extract entities from this.
- `start_long_term_update(session_id=..., reason="reusable_pattern", summary="...")` — you found a workflow worth reusing. The system will generate a SOP Skill from this.
- `start_long_term_update(session_id=..., reason="fault_recovery", summary="...")` — you recovered from an error. The system records the fix pattern.

**After discovering new knowledge:**
- `entity_manage(action="create", entity_id=..., entity_type=..., name=..., content=..., properties=...)` — create L2 entities for newly discovered services, configs, people, tools.
- `entity_manage(action="link", entity_id=..., relation="MANAGES|DEPENDS_ON|CAUSED_BY|...", target_entity_id=...)` — link related entities with meaningful relationship types.
- `skill_manage(action="register", skill_id=..., name=..., category=..., description=..., content=...)` — register a new Skill. Write the SKILL.md content yourself, or leave empty for a basic template.
- `start_long_term_update(reason="reusable_pattern", summary="...", skill_id="category/name")` — queue Skill evolution. Include skill_id to target a specific Skill, or omit to auto-detect from session.

**After finding cross-domain patterns:**
- `meta_pattern(action="create", pattern_id=..., name=..., description=..., abstract_steps=[...], source_skills=[...])` — when you notice the same strategy pattern across multiple Skills.

**Key timing rules:**
- Write to memory AFTER execution succeeds, never before.
- Only store knowledge with cross-task reuse value. One-off context is noise.

## Available Tools
{tool_descriptions}

## Session Context
{history_summary}

## Working Memory
Session ID: {session_id}
Turn: {turn_number}
Recent: {recent_summaries}
Key Info: {key_info}
"""


class ContextBuilder:
    def __init__(self, dispatcher: ToolDispatcher, agent_name: str = "Noesis"):
        self._dispatcher = dispatcher
        self._agent_name = agent_name
        self._tool_descriptions = self._build_tool_descriptions()

    def _build_tool_descriptions(self) -> str:
        lines = []
        for schema in self._dispatcher.get_schemas():
            f = schema["function"]
            lines.append(f"- **{f['name']}**: {f['description']}")
        return "\n".join(lines)

    def build_system_prompt(
        self,
        turn_number: int = 0,
        recent_summaries: str = "(none)",
        key_info: str = "(no key info yet)",
        history_summary: str = "",
        session_id: str = "",
        l1_skills: str = "(no skills registered yet)",
    ) -> str:
        return SYSTEM_PROMPT.format(
            agent_name=self._agent_name,
            tool_descriptions=self._tool_descriptions,
            turn_number=turn_number,
            recent_summaries=recent_summaries,
            key_info=key_info,
            history_summary=history_summary or "(new session)",
            session_id=session_id,
            l1_skills=l1_skills,
        )

    def build_messages(
        self,
        user_message: str,
        history: list[Message],
        turn_number: int = 0,
        recent_summaries: str = "(none)",
        key_info: str = "(no key info yet)",
        history_summary: str = "",
        session_id: str = "",
        l1_skills: str = "(no skills registered yet)",
    ) -> list[Message]:
        system = self.build_system_prompt(
            turn_number, recent_summaries, key_info, history_summary, session_id, l1_skills,
        )
        messages = [Message.text_msg("system", system)]
        messages.extend(history)
        if user_message:
            messages.append(Message.text_msg("user", user_message))
        return messages

    def wrap_tool_result(self, tool_name: str, tool_output: str, call_id: str) -> Message:
        return Message.tool_result_msg("system", call_id, tool_name, tool_output)

    def wrap_assistant(self, content: str | None, tool_calls) -> Message:
        if tool_calls:
            text = "\n".join(f"[ToolCall: {tc.name}({tc.arguments})]" for tc in tool_calls)
            return Message.text_msg("assistant", content or text)
        return Message.text_msg("assistant", content or "")
