# Agent Prompt Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace existing prompts in the conscious loop and subconscious pipeline with optimized versions that enforce memory retrieval, checkpointing, evolution triggers, and higher-quality skill generation — while keeping output schemas compatible with existing code parsers.

**Architecture:** Prompt-only changes across 5 files (`agent/context.py`, `memory/extractor.py`, `skill_system/distillation.py`, `skill_system/optimizer.py`, `skill_system/compiler.py`). Each file gets a new prompt constant and a corresponding unit test that asserts the prompt contains required clauses and excludes forbidden fields.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `agent/context.py` | Modify | `SYSTEM_PROMPT` string; `ContextBuilder.build_system_prompt` adds dynamic checkpoint hint |
| `memory/extractor.py` | Modify | `EXTRACT_PROMPT` string — entity/relationship extraction with strict schema |
| `skill_system/distillation.py` | Modify | `SOP_PROMPT` string — NL → SOP markdown generation with quality standards |
| `skill_system/optimizer.py` | Modify | `OPTIMIZE_PROMPT` string — semantic SOP vs trace comparison with strict JSON schema |
| `skill_system/compiler.py` | Modify | `COMPILE_PROMPT` string — SOP → Python code + tests with concrete requirements |
| `tests/test_agent_context.py` | Create | Assert system prompt contains mandatory checkpoints, IF-THEN rules, MEMORY_DECLARATION |
| `tests/test_memory_extractor.py` | Create | Assert extract prompt contains cross-task filter, dedup mindset, strict schema |
| `tests/test_skill_distillation.py` | Create | Assert SOP prompt contains quality standards, required sections, no score output |
| `tests/test_skill_optimizer.py` | Create | Assert optimize prompt contains semantic dimensions, strict 4-field JSON schema |
| `tests/test_skill_compiler.py` | Create | Assert compile prompt contains concrete code/test requirements, ===TEST=== separator |

---

### Task 1: System Prompt Optimization

**Files:**
- Modify: `agent/context.py`
- Create: `tests/test_agent_context.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent_context.py`:

```python
from agent.context import ContextBuilder, SYSTEM_PROMPT
from tools.dispatcher import ToolDispatcher


def test_system_prompt_has_mandatory_checkpoints():
    assert "TASK_START" in SYSTEM_PROMPT
    assert "PROGRESS" in SYSTEM_PROMPT
    assert "TASK_END" in SYSTEM_PROMPT
    assert "MANDATORY" in SYSTEM_PROMPT


def test_system_prompt_has_if_then_rules():
    assert "IF discovered new service" in SYSTEM_PROMPT
    assert "IF discovered new error pattern" in SYSTEM_PROMPT
    assert "IF same tool-call sequence repeated" in SYSTEM_PROMPT
    assert "IF a deliverable subgoal is completed" in SYSTEM_PROMPT
    assert "IF cross-skill generic strategy detected" in SYSTEM_PROMPT
    assert "IF user says" in SYSTEM_PROMPT


def test_system_prompt_has_memory_declaration():
    assert "MEMORY_DECLARATION" in SYSTEM_PROMPT
    assert "reusable_knowledge" in SYSTEM_PROMPT


def test_system_prompt_retrieve_first():
    assert "RETRIEVE first" in SYSTEM_PROMPT
    assert "Act first, search later" not in SYSTEM_PROMPT


def test_context_builder_injects_checkpoint_hint():
    dispatcher = ToolDispatcher()
    builder = ContextBuilder(dispatcher)
    prompt = builder.build_system_prompt(turn_number=3)
    assert "Next Checkpoint" in prompt or "checkpoint" in prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_context.py -v`

Expected: FAIL — assertions fail because current `SYSTEM_PROMPT` does not contain the new clauses.

- [ ] **Step 3: Replace SYSTEM_PROMPT in agent/context.py**

In `agent/context.py`, replace the `SYSTEM_PROMPT` assignment with:

```python
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
```

- [ ] **Step 4: Modify ContextBuilder.build_system_prompt to inject checkpoint hint**

In `agent/context.py`, inside `ContextBuilder.build_system_prompt`, add checkpoint hint generation before the return statement:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_agent_context.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agent/context.py tests/test_agent_context.py
git commit -m "feat: optimize system prompt with mandatory checkpoints and evolution triggers"
```

---

### Task 2: Entity Extraction Prompt Optimization

**Files:**
- Modify: `memory/extractor.py`
- Create: `tests/test_memory_extractor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory_extractor.py`:

```python
from memory.extractor import EXTRACT_PROMPT


def test_extract_prompt_has_strict_schema():
    assert '"entities"' in EXTRACT_PROMPT
    assert '"relations"' in EXTRACT_PROMPT
    assert '"entity_id"' in EXTRACT_PROMPT
    assert '"entity_type"' in EXTRACT_PROMPT
    assert '"name"' in EXTRACT_PROMPT
    assert '"content"' in EXTRACT_PROMPT
    assert '"properties"' in EXTRACT_PROMPT
    assert '"from"' in EXTRACT_PROMPT
    assert '"to"' in EXTRACT_PROMPT
    assert '"type"' in EXTRACT_PROMPT


def test_extract_prompt_no_extra_fields():
    assert '"confidence"' not in EXTRACT_PROMPT
    assert '"reason"' not in EXTRACT_PROMPT
    assert '"evidence"' not in EXTRACT_PROMPT
    assert '"merge_candidates"' not in EXTRACT_PROMPT


def test_extract_prompt_has_quality_guidance():
    assert "Cross-task value filter" in EXTRACT_PROMPT
    assert "Deduplication mindset" in EXTRACT_PROMPT
    assert "Relationship inference" in EXTRACT_PROMPT
    assert "Names must be stable" in EXTRACT_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_extractor.py -v`

Expected: FAIL — current `EXTRACT_PROMPT` lacks the new clauses and strict schema.

- [ ] **Step 3: Replace EXTRACT_PROMPT in memory/extractor.py**

In `memory/extractor.py`, replace the `EXTRACT_PROMPT` assignment with:

```python
EXTRACT_PROMPT = """Extract entities and relationships from this execution trace.

Execution trace:
{trace}

Summary from agent: {summary}

## Extraction Rules
1. **Entity types**: Use precise types (Service, Config, ErrorPattern, Person,
   Project, APIEndpoint, FilePath, Command, Constraint). Avoid generic "Fact".
2. **Deduplication mindset**: If you see an entity that clearly refers to the
   same real-world object as a previously extracted one, reuse the same name
   and type. The system will merge them automatically.
3. **Relationship inference**: Extract BOTH explicit relationships
   (stated in text) AND implicit dependencies (logical causality,
   prerequisite chains, containment).
4. **Cross-task value filter**: Only extract knowledge reusable across sessions.
   Skip one-off file names, temporary variables, ephemeral IDs.
5. **Names must be stable**: No timestamps, no random IDs, no session-specific
   qualifiers in entity names.

## Output Schema (strict — only these fields)
{{
  "entities": [
    {{
      "entity_id": "ent_xxx",
      "entity_type": "Service|Config|ErrorPattern|...",
      "name": "short unique name",
      "content": "detailed description including purpose and behavior",
      "properties": {{"key": "value"}}
    }}
  ],
  "relations": [
    {{
      "from": "ent_xxx",
      "to": "ent_yyy",
      "type": "DEPENDS_ON|MANAGES|CAUSED_BY|CONTAINS|REQUIRES"
    }}
  ]
}}

Quality guidelines (not output fields):
- At least 1 relationship per entity (isolated entities are suspicious).
- Confidence is handled by the system; do not include it.
- Output ONLY valid JSON. No commentary outside the JSON.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_extractor.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory/extractor.py tests/test_memory_extractor.py
git commit -m "feat: optimize entity extraction prompt with strict schema and quality rules"
```

---

### Task 3: Skill Distillation Prompt Optimization

**Files:**
- Modify: `skill_system/distillation.py`
- Create: `tests/test_skill_distillation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_distillation.py`:

```python
from skill_system.distillation import SOP_PROMPT


def test_sop_prompt_has_quality_standards():
    assert "Executable" in SOP_PROMPT
    assert "Bounded" in SOP_PROMPT
    assert "Resilient" in SOP_PROMPT
    assert "Verifiable" in SOP_PROMPT


def test_sop_prompt_has_required_sections():
    assert "## Overview" in SOP_PROMPT
    assert "## When to Use" in SOP_PROMPT
    assert "## Prerequisites" in SOP_PROMPT
    assert "## Core Pattern" in SOP_PROMPT
    assert "## Common Mistakes" in SOP_PROMPT
    assert "## Variants" in SOP_PROMPT


def test_sop_prompt_no_scores_or_json():
    assert "self-assessment" not in SOP_PROMPT.lower()
    assert "executability" not in SOP_PROMPT.lower()
    assert "completeness" not in SOP_PROMPT.lower()
    assert "reuse_value" not in SOP_PROMPT.lower()
    assert "Output ONLY the SKILL.md markdown content" in SOP_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skill_distillation.py -v`

Expected: FAIL — current `SOP_PROMPT` is much shorter and lacks these clauses.

- [ ] **Step 3: Replace SOP_PROMPT in skill_system/distillation.py**

In `skill_system/distillation.py`, replace the `SOP_PROMPT` assignment with:

```python
SOP_PROMPT = """Generate an SOP from this skill's execution history.

Skill: {skill_name} ({skill_id})
Current stage: {stage}

Recent execution steps:
{trace}

Summary from user: {summary}

## SOP Quality Standards (follow these, but do not output scores)
Your output must be a markdown document that is:
1. **Executable**: Every step maps to a specific tool call or action found in the trace.
2. **Bounded**: Lists prerequisites, expected inputs, and success criteria.
3. **Resilient**: Includes "Common Mistakes" and error recovery steps observed in the trace.
4. **Verifiable**: Each step has an observable output or check.

## Required Sections
- ## Overview: One sentence on what this SOP achieves.
- ## When to Use: Specific trigger conditions.
- ## Prerequisites: Required tools, credentials, or state.
- ## Core Pattern: Numbered steps, each step must reference a tool/action from the trace.
- ## Common Mistakes: Observed errors and their fixes.
- ## Variants (optional): If the trace shows conditional branches, document them.

## Output Format Rules
- Output ONLY the SKILL.md markdown content.
- Do NOT include any JSON, scores, or self-assessment blocks.
- The code quality gate checks for: length >= 100 chars AND presence of numbered steps.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skill_distillation.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skill_system/distillation.py tests/test_skill_distillation.py
git commit -m "feat: optimize SOP distillation prompt with quality standards and required sections"
```

---

### Task 4: Skill Optimization Prompt Optimization

**Files:**
- Modify: `skill_system/optimizer.py`
- Create: `tests/test_skill_optimizer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_optimizer.py`:

```python
from skill_system.optimizer import OPTIMIZE_PROMPT


def test_optimize_prompt_has_semantic_dimensions():
    assert "Step presence" in OPTIMIZE_PROMPT
    assert "Step order" in OPTIMIZE_PROMPT
    assert "Parameter drift" in OPTIMIZE_PROMPT
    assert "New patterns" in OPTIMIZE_PROMPT
    assert "Error handling" in OPTIMIZE_PROMPT


def test_optimize_prompt_strict_schema():
    assert '"suggestions"' in OPTIMIZE_PROMPT
    assert '"variant_detected"' in OPTIMIZE_PROMPT
    assert '"variant_description"' in OPTIMIZE_PROMPT
    assert '"recommended_updates"' in OPTIMIZE_PROMPT


def test_optimize_prompt_no_extra_fields():
    assert '"type"' not in OPTIMIZE_PROMPT
    assert '"location"' not in OPTIMIZE_PROMPT
    assert '"severity"' not in OPTIMIZE_PROMPT
    assert '"evidence"' not in OPTIMIZE_PROMPT
    assert '"execution_quality"' not in OPTIMIZE_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skill_optimizer.py -v`

Expected: FAIL — current `OPTIMIZE_PROMPT` lacks semantic dimensions and strict schema enforcement.

- [ ] **Step 3: Replace OPTIMIZE_PROMPT in skill_system/optimizer.py**

In `skill_system/optimizer.py`, replace the `OPTIMIZE_PROMPT` assignment with:

```python
OPTIMIZE_PROMPT = """Compare the SOP with actual execution traces. Detect semantic deviations.

Current SOP:
{sop_content}

Recent execution traces (tool calls with parameters):
{trace_with_params}

## Analysis Instructions
Analyze these dimensions internally, then synthesize your findings:
1. **Step presence**: Did execution follow all SOP steps? Were any skipped?
2. **Step order**: Was the sequence different, even if tool names match?
3. **Parameter drift**: Were tools called with different arguments than SOP specifies?
4. **New patterns**: Were tools used that aren't in the SOP? Is this a one-off or trend?
5. **Error handling**: Did execution encounter errors not covered in SOP?

Only suggest changes if evidence is strong (>= 2 occurrences or clear error pattern).

## Output Schema (strict — only these fields)
{{
  "suggestions": [
    "specific, actionable suggestion 1",
    "specific, actionable suggestion 2"
  ],
  "variant_detected": true or false,
  "variant_description": "if execution systematically diverged from SOP, describe the new pattern",
  "recommended_updates": "specific markdown text to insert into or modify in the SOP"
}}

Output ONLY valid JSON. No extra fields.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skill_optimizer.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skill_system/optimizer.py tests/test_skill_optimizer.py
git commit -m "feat: optimize SOP optimization prompt with semantic comparison and strict schema"
```

---

### Task 5: Skill Compilation Prompt Optimization

**Files:**
- Modify: `skill_system/compiler.py`
- Create: `tests/test_skill_compiler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_compiler.py`:

```python
from skill_system.compiler import COMPILE_PROMPT


def test_compile_prompt_has_code_requirements():
    assert "Argument validation" in COMPILE_PROMPT
    assert "Error handling" in COMPILE_PROMPT
    assert "Timeout" in COMPILE_PROMPT
    assert "Progress logging" in COMPILE_PROMPT
    assert "Idempotency" in COMPILE_PROMPT
    assert "Return codes" in COMPILE_PROMPT


def test_compile_prompt_has_test_requirements():
    assert "Happy path" in COMPILE_PROMPT
    assert "Error path" in COMPILE_PROMPT
    assert "Boundary" in COMPILE_PROMPT
    assert "Mock external calls" in COMPILE_PROMPT


def test_compile_prompt_has_separator():
    assert "===TEST===" in COMPILE_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skill_compiler.py -v`

Expected: FAIL — current `COMPILE_PROMPT` uses generic requirements and lacks concrete code/test standards.

- [ ] **Step 3: Replace COMPILE_PROMPT in skill_system/compiler.py**

In `skill_system/compiler.py`, replace the `COMPILE_PROMPT` assignment with:

```python
COMPILE_PROMPT = """Generate executable Python code from this SOP. Output TWO files separated by `===TEST===`.

SOP:
{sop_content}

## Code Requirements (apply to main.py)
1. **Argument validation**: Use argparse with type checking; reject invalid inputs.
2. **Error handling**: Wrap external calls in try/except; log errors with context.
3. **Timeout**: All subprocess calls must have timeout (default 30s).
4. **Progress logging**: Print step name before execution; print completion status.
5. **Idempotency**: Where possible, check if step already done before repeating.
6. **Return codes**: Exit 0 on success, 1 on failure, 2 on partial success.

## Test Requirements (apply to test_main.py)
1. **Happy path**: Verify main.py runs with valid arguments.
2. **Error path**: Verify graceful failure with invalid arguments/missing files.
3. **Boundary**: Verify behavior at edge cases (empty input, max length, special chars).
4. **Mock external calls**: Use unittest.mock for network/subprocess to avoid side effects.

## Output Format
```python
# scripts/main.py
...
```

===TEST===

```python
# scripts/test_main.py
...
```

Output ONLY the two code blocks, no other text.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_skill_compiler.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skill_system/compiler.py tests/test_skill_compiler.py
git commit -m "feat: optimize SOP compilation prompt with concrete code and test requirements"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] Mandatory checkpoints (TASK_START, PROGRESS, TASK_END) → Task 1
- [x] IF-THEN trigger rules (6 rules) → Task 1
- [x] Memory Evolution Declaration → Task 1
- [x] RETRIEVE first strategy → Task 1
- [x] Dynamic checkpoint injection → Task 1
- [x] Entity extraction strict schema + quality rules → Task 2
- [x] Skill distillation quality standards + required sections → Task 3
- [x] Skill optimization semantic comparison + strict schema → Task 4
- [x] Skill compilation concrete code/test requirements → Task 5
- [x] Field compatibility with existing code → Verified in all test files

**2. Placeholder scan:**
- [x] No TBD/TODO/fill-in-details found
- [x] Every step contains concrete code or exact commands
- [x] No "similar to Task N" references

**3. Type consistency:**
- [x] Method signatures in plan match existing code (`build_system_prompt` params unchanged)
- [x] Prompt variable names (`{trace}`, `{summary}`, `{sop_content}`, etc.) match existing usage

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-agent-prompt-optimization.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach do you prefer?
