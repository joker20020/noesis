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
    assert "checkpoint" in prompt.lower()
