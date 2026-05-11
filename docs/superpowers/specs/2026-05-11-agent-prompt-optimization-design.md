# Agent Prompt Optimization Design

## Overview

优化 Noesis Agent 系统的提示词设计，解决显意识循环中 Agent **不主动搜索记忆、任务完成后不总结、不添加检查点**的问题，同时提升潜意识管线（实体抽取、Skill 蒸馏/优化/编译）的提示词质量，实现自动图谱记忆和自进化功能。

**核心策略**：显意识触发请求 + 潜意识处理进化。提示词改动集中，不修改核心循环架构。

---

## Problem Statement

当前系统存在以下问题：

1. **记忆搜索被动**：系统提示词主张 "Act first, search later"，导致 Agent 在多数任务中跳过记忆检索，无法利用 L1-L4 知识。
2. **缺乏强制总结机制**：任务完成后没有结构化总结要求，执行轨迹的价值未被提取。
3. **检查点添加随意**：`update_working_checkpoint` 的使用依赖 Agent 自主判断，缺乏强制时机。
4. **自动图谱记忆未生效**：虽然系统提示词列出了记忆进化工具，但 Agent 很少主动调用 `entity_manage`、`start_long_term_update` 等。
5. **Skill 自进化管线提示词质量不足**：蒸馏生成的 SOP 过于笼统；优化仅对比工具名序列，无法检测语义偏差；编译生成的代码健壮性不足。

---

## Design Approach

采用 **混合分层模式（Hybrid Tiered）**：

- **显意识侧**：用 "3 个强制检查点 + 6 条 IF-THEN 规则 + 1 个进化声明" 替代松散的 "When to..." 建议。
- **潜意识侧**：升级提示词的约束强度、分析深度和质量引导，但**输出字段严格与现有代码匹配**，不引入代码无法解析的新字段。

---

## System Prompt Design (Conscious Loop)

### 1. Mandatory Checkpoints

在提示词中以 `⚠️ MANDATORY` 标记三个不可跳过的检查时机：

| Checkpoint | Trigger Condition | Required Action |
|---|---|---|
| **TASK_START** | `turn_number == 1` OR user input references entities/configs/history | Call `memory_search` across L1-L4; if matching Skill exists, load its SOP |
| **PROGRESS** | `turn_number % 5 == 0` AND task incomplete | Call `update_working_checkpoint` with current findings, blockers, next steps |
| **TASK_END** | No further `tool_calls` (natural completion) OR user expresses satisfaction | Generate structured summary; answer Memory Evolution Declaration; call `start_long_term_update` if applicable |

### 2. IF-THEN Trigger Rules

Replace vague "when to evolve" guidance with explicit condition-action pairs:

```
IF discovered new service/config/API endpoint/person/project
   THEN call entity_manage(action="create") immediately

IF discovered new error pattern or recovery steps
   THEN call entity_manage + start_long_term_update(reason="fault_recovery")

IF same tool-call sequence repeated >= 3 times for similar tasks
   THEN on task end call start_long_term_update(reason="reusable_pattern")

IF a deliverable subgoal is completed (bug fixed, service configured, etc.)
   THEN call start_long_term_update(reason="subgoal_completed")

IF cross-skill generic strategy detected
   THEN call meta_pattern(action="create")

IF user says "remember this" or "I'll need this again"
   THEN immediately trigger corresponding long-term update
```

### 3. Memory Evolution Declaration

At `TASK_END` checkpoint, force the following structured answer before completing:

```
[MEMORY_DECLARATION]
- reusable_knowledge: yes / no
- type: entity | skill | pattern | none
- reason: one sentence explaining why
```

### 4. Search Strategy Inversion

Change from:
> "Act first, search later"

To:
> "RETRIEVE first, act with context. Default to searching memory on turn 1. Skip only for obviously single-turn queries (greetings, current time, trivial questions)."

### 5. Dynamic Context Injection

To prevent prompt bloat, `ContextBuilder` dynamically injects checkpoint proximity hints into the `Working Memory` block:

```
Working Memory
Session ID: {session_id}
Turn: {turn_number}
Recent: {recent_summaries}
Key Info: {key_info}
Next Checkpoint: PROGRESS_CHECK at turn 5 (current: 3)
```

---

## Subconscious Pipeline Prompt Design

**Constraint**: All prompt outputs must match fields parsed by existing code. No extra fields.

### Entity Extraction (`EXTRACT_PROMPT`)

**Code uses**: `entities[]` with `entity_id`, `entity_type`, `name`, `content`, `properties`; `relations[]` with `from`, `type`, `to`.

**Prompt structure**:

```markdown
Extract entities and relationships from this execution trace.

Execution trace:
{trace}

Summary from agent: {summary}

## Extraction Rules
1. Entity types: Use precise types (Service, Config, ErrorPattern, Person,
   Project, APIEndpoint, FilePath, Command, Constraint). Avoid generic "Fact".
2. Deduplication mindset: If an entity clearly refers to the same real-world
   object as a previously extracted one, reuse the same name and type.
   The system will merge them automatically.
3. Relationship inference: Extract BOTH explicit relationships (stated in text)
   AND implicit dependencies (logical causality, prerequisite chains, containment).
4. Cross-task value filter: Only extract knowledge reusable across sessions.
   Skip one-off file names, temporary variables, ephemeral IDs.
5. Names must be stable: No timestamps, no random IDs, no session-specific
   qualifiers in entity names.

## Output Schema (strict — only these fields)
{
  "entities": [
    {
      "entity_id": "ent_xxx",
      "entity_type": "Service|Config|ErrorPattern|...",
      "name": "short unique name",
      "content": "detailed description including purpose and behavior",
      "properties": {"key": "value"}
    }
  ],
  "relations": [
    {
      "from": "ent_xxx",
      "to": "ent_yyy",
      "type": "DEPENDS_ON|MANAGES|CAUSED_BY|CONTAINS|REQUIRES"
    }
  ]
}

Quality guidelines (not output fields):
- At least 1 relationship per entity (isolated entities are suspicious).
- Confidence is handled by the system; do not include it.
- Output ONLY valid JSON. No commentary outside the JSON.
```

**Improvements over current prompt**:
- Added precise type enumeration and cross-task value filter.
- Moved quality guidance (relationship coverage, stable names) into instruction text rather than output fields.
- Added deduplication mindset to reduce duplicate entities.

### Skill Distillation (`SOP_PROMPT`)

**Code uses**: Full markdown text stored directly to `SKILL.md`. Quality gate checks length >= 100 and presence of step markers ("1.", "Step 1", "### Steps", "## Core Pattern").

**Prompt structure**:

```markdown
Generate an SOP from this skill's execution history.

Skill: {skill_name} ({skill_id})
Current stage: {stage}

Recent execution steps:
{trace}

Summary from user: {summary}

## SOP Quality Standards (follow these, but do not output scores)
Your output must be a markdown document that is:
1. Executable: Every step maps to a specific tool call or action found in the trace.
2. Bounded: Lists prerequisites, expected inputs, and success criteria.
3. Resilient: Includes "Common Mistakes" and error recovery steps observed in the trace.
4. Verifiable: Each step has an observable output or check.

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
```

**Improvements over current prompt**:
- Explicit quality standards (executable, bounded, resilient, verifiable) guide content generation.
- Required sections ensure consistent structure.
- Clarified that output is pure markdown, no JSON.

### Skill Optimization (`OPTIMIZE_PROMPT`)

**Code uses**: `suggestions` (string array), `variant_detected` (bool), `variant_description` (string), `recommended_updates` (string).

**Prompt structure**:

```markdown
Compare the SOP with actual execution traces. Detect semantic deviations.

Current SOP:
{sop_content}

Recent execution traces (tool calls with parameters):
{trace_with_params}

## Analysis Instructions
Analyze these dimensions internally, then synthesize your findings:
1. Step presence: Did execution follow all SOP steps? Were any skipped?
2. Step order: Was the sequence different, even if tool names match?
3. Parameter drift: Were tools called with different arguments than SOP specifies?
4. New patterns: Were tools used that aren't in the SOP? Is this a one-off or trend?
5. Error handling: Did execution encounter errors not covered in SOP?

Only suggest changes if evidence is strong (>= 2 occurrences or clear error pattern).

## Output Schema (strict — only these fields)
{
  "suggestions": [
    "specific, actionable suggestion 1",
    "specific, actionable suggestion 2"
  ],
  "variant_detected": true or false,
  "variant_description": "if execution systematically diverged from SOP, describe the new pattern",
  "recommended_updates": "specific markdown text to insert into or modify in the SOP"
}

Output ONLY valid JSON. No extra fields.
```

**Improvements over current prompt**:
- Upgraded from tool-name sequence comparison to semantic comparison (parameter drift, step order, presence).
- Added analysis dimensions in instruction text to guide LLM reasoning without adding output fields.
- Kept output schema strictly matching code parser.

### Skill Compilation (`COMPILE_PROMPT`)

**Code uses**: Text split by `===TEST===`, then two ` ```python ` code blocks extracted.

**Prompt structure**:

```markdown
Generate executable Python code from this SOP. Output TWO files separated by `===TEST===`.

SOP:
{sop_content}

## Code Requirements (apply to main.py)
1. Argument validation: Use argparse with type checking; reject invalid inputs.
2. Error handling: Wrap external calls in try/except; log errors with context.
3. Timeout: All subprocess calls must have timeout (default 30s).
4. Progress logging: Print step name before execution; print completion status.
5. Idempotency: Where possible, check if step already done before repeating.
6. Return codes: Exit 0 on success, 1 on failure, 2 on partial success.

## Test Requirements (apply to test_main.py)
1. Happy path: Verify main.py runs with valid arguments.
2. Error path: Verify graceful failure with invalid arguments/missing files.
3. Boundary: Verify behavior at edge cases (empty input, max length, special chars).
4. Mock external calls: Use unittest.mock for network/subprocess to avoid side effects.

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
```

**Improvements over current prompt**:
- Specific code requirements (argparse, timeouts, idempotency, return codes) instead of generic "proper error handling".
- Specific test requirements (happy path, error path, boundary, mocking) instead of generic "verify basic output".
- No JSON output; format remains compatible with existing `_extract_code` logic.

---

## Compatibility with Existing Code

| Prompt | Output Format | Fields Used by Code | Fields Removed to Match Code |
|---|---|---|---|
| Entity Extraction | JSON | `entities` (id, type, name, content, properties), `relations` (from, type, to) | `confidence`, `reason`, `evidence`, `merge_candidates` |
| Skill Distillation | Markdown | Full text stored to `SKILL.md` | Self-assessment scores, JSON blocks |
| Skill Optimization | JSON | `suggestions`, `variant_detected`, `variant_description`, `recommended_updates` | `type`, `location`, `severity`, `evidence`, `execution_quality` |
| Skill Compilation | Code blocks split by `===TEST===` | Two ` ```python ` blocks | None (already compatible) |

All quality guidance, analysis dimensions, and constraints are expressed in **instruction text** to influence LLM generation behavior, not in **output fields** that would require code changes.

---

## Quality Gate Integration

The subconscious pipeline operates with the following existing gates (no code changes required):

| Stage | Existing Gate | How Prompt Helps |
|---|---|---|
| Entity Extraction | Merge by name+type, boost confidence | Prompt guides stable naming and relationship extraction |
| NL -> SOP | Length >= 100 AND has step markers | Prompt quality standards increase pass rate |
| SOP -> Optimize | Execute on every distillation tick | Semantic analysis in prompt produces better suggestions |
| SOP -> CODE | Confidence >= 0.8 AND usage >= 5 AND tests pass | Better SOP quality indirectly improves compile success |

---

## Files to Modify

1. `agent/context.py` — `SYSTEM_PROMPT` and `ContextBuilder`
2. `memory/extractor.py` — `EXTRACT_PROMPT`
3. `skill_system/distillation.py` — `SOP_PROMPT`
4. `skill_system/optimizer.py` — `OPTIMIZE_PROMPT`
5. `skill_system/compiler.py` — `COMPILE_PROMPT`

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| System prompt length increase dilutes attention | Use dynamic context injection (checkpoint hints in Working Memory block only) rather than expanding static prompt |
| "RETRIEVE first" causes over-searching on trivial queries | Exception clause: "Skip only for obviously single-turn queries (greetings, current time)" |
| Mandatory checkpoints add tool calls and latency | PROGRESS check only every 5 turns; TASK_END check is natural completion boundary |
| Agent ignores MANDATORY markers | Use strong imperative language ("You MUST", "Do NOT skip") and dynamic proximity hints |

---

## Success Criteria

1. Agent calls `memory_search` on turn 1 for >= 80% of multi-turn tasks.
2. `update_working_checkpoint` is called at least once per session lasting > 5 turns.
3. `start_long_term_update` is triggered on >= 50% of task completions.
4. SOP distillation pass rate (length + step markers) improves from baseline.
5. Compiled Skill test pass rate improves from baseline.
