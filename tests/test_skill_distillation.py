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
