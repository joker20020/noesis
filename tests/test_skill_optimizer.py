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
