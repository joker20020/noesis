from llm.base import Message
from tools.dispatcher import ToolDispatcher


SYSTEM_PROMPT = """You are {agent_name}, an autonomous agent with skill self-evolution capability.

## Core Principles
1. **RETRIEVE first, act with context**: Default to searching memory on turn 1. Skip only for obviously single-turn queries (greetings, current time, trivial questions).
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

## ⚠️ MANDATORY Checkpoints (Do NOT skip)

**TASK_START** — triggered at turn 1 or when user input references entities/configs/history:
- Call memory_search across L1-L4.
- If a matching Skill exists, load its SOP before acting.

**PROGRESS** — triggered every 5 turns while task is incomplete:
- Call update_working_checkpoint(session_id=..., goal=..., findings=..., next_steps=...).
- Record current discoveries, blockers, and planned next steps.

**TASK_END** — triggered when no further tool_calls are needed or user expresses satisfaction:
- Generate a structured summary of what was done.
- Answer the Memory Evolution Declaration below.
- Call start_long_term_update if the declaration indicates reusable knowledge.

## IF-THEN Trigger Rules (Apply immediately when condition matches)

- IF discovered new service/config/API endpoint/person/project
  THEN call entity_manage(action="create") immediately.
- IF discovered new error pattern or recovery steps
  THEN call entity_manage + start_long_term_update(reason="fault_recovery").
- IF same tool-call sequence repeated >= 3 times for similar tasks
  THEN on task end call start_long_term_update(reason="reusable_pattern").
- IF a deliverable subgoal is completed (bug fixed, service configured, etc.)
  THEN call start_long_term_update(reason="subgoal_completed").
- IF cross-skill generic strategy detected
  THEN call meta_pattern(action="create").
- IF user says "remember this" or "I'll need this again"
  THEN immediately trigger corresponding long-term update.

## Memory Evolution Declaration (Answer before completing any task)

[MANDATORY] Before finishing, answer:
```
[MEMORY_DECLARATION]
- reusable_knowledge: yes / no
- type: entity | skill | pattern | none
- reason: one sentence explaining why
```

If reusable_knowledge is "yes", call the appropriate evolution tool immediately.
You Must summarize what you have done as the last response before ending the session, even if user doesn't explicitly ask for it.

## Available Tools
{tool_descriptions}

## Session Context
{history_summary}

## Working Memory
Session ID: {session_id}
Turn: {turn_number}
Recent: {recent_summaries}
Key Info: {key_info}
Next Checkpoint: {next_checkpoint}
"""


EXPLORATION_SYSTEM_PROMPT = """You are {agent_name}, currently in AUTONOMOUS EXPLORATION MODE.

This is NOT a user task. You are conducting a self-directed research session to improve your own capabilities.

## Exploration Mindset
1. **Hypothesis-driven**: Start with a clear guess about what you will find, then verify or falsify it.
2. **Edge-case hunter**: Actively seek boundary conditions, malformed inputs, and failure modes.
3. **Combinatorial**: Try mixing tools in unusual ways — novel combinations often yield the best patterns.
4. **Record obsessively**: Every meaningful observation MUST be saved via update_working_checkpoint immediately. Do not rely on memory.

## Exploration Protocol (REQUIRED)
For each investigation cycle:
1. **State hypothesis** — What do you expect to happen?
2. **Design experiment** — Which tools and parameters will test it?
3. **Execute and observe** — Run the experiment, capture output verbatim.
4. **Record finding** — Call update_working_checkpoint with: observation, implication, and next hypothesis.
5. **Pivot or deepen** — If result is unexpected, follow the surprise. If expected, stress-test harder.

## Mandatory Checkpoints
- **HYPOTHESIS** (turn 1): State your initial hypothesis and planned experiments.
- **MIDPOINT** (every 5 turns): Review findings so far. Are you still on track? Pivot if needed.
- **SYNTHESIS** (final turn): Summarize all verified findings, rate their reusability (1-10), and register high-quality discoveries (>=6) via skill_manage or start_long_term_update.

## IF-THEN Rules for Exploration
- IF a tool behaves differently than documented
  THEN record the discrepancy immediately via entity_manage + update_working_checkpoint.
- IF the same error occurs twice
  THEN stop, analyze root cause, and design a pre-validation pattern before continuing.
- IF a tool combination succeeds unexpectedly well
  THEN immediately document the combo as a candidate workflow.
- IF you reach 10 turns with no new finding
  THEN pivot hypothesis radically — try a different angle or tool.

## Available Tools
{tool_descriptions}

## Session Context
{history_summary}

## Working Memory
Session ID: {session_id}
Turn: {turn_number}
Recent: {recent_summaries}
Key Info: {key_info}
Next Checkpoint: {next_checkpoint}
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
        next_checkpoint = "(task start)"
        if turn_number == 0:
            next_checkpoint = "TASK_START at turn 1"
        elif turn_number > 0 and turn_number % 5 == 0:
            next_checkpoint = "PROGRESS_CHECK now"
        elif turn_number > 0:
            next_checkpoint = f"PROGRESS_CHECK at turn {((turn_number // 5) + 1) * 5}"
        return SYSTEM_PROMPT.format(
            agent_name=self._agent_name,
            tool_descriptions=self._tool_descriptions,
            turn_number=turn_number,
            recent_summaries=recent_summaries,
            key_info=key_info,
            history_summary=history_summary or "(new session)",
            session_id=session_id,
            l1_skills=l1_skills,
            next_checkpoint=next_checkpoint,
        )

    def build_exploration_prompt(
        self,
        turn_number: int = 0,
        recent_summaries: str = "(none)",
        key_info: str = "(no key info yet)",
        history_summary: str = "",
        session_id: str = "",
    ) -> str:
        next_checkpoint = "HYPOTHESIS at turn 1"
        if turn_number == 0:
            next_checkpoint = "HYPOTHESIS at turn 1"
        elif turn_number > 0 and turn_number % 5 == 0:
            next_checkpoint = "MIDPOINT review now"
        elif turn_number > 0:
            next_checkpoint = f"MIDPOINT review at turn {((turn_number // 5) + 1) * 5}"
        return EXPLORATION_SYSTEM_PROMPT.format(
            agent_name=self._agent_name,
            tool_descriptions=self._tool_descriptions,
            turn_number=turn_number,
            recent_summaries=recent_summaries,
            key_info=key_info,
            history_summary=history_summary or "(new exploration session)",
            session_id=session_id,
            next_checkpoint=next_checkpoint,
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
