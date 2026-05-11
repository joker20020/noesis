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
