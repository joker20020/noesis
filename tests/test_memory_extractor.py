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
