"""Judge-layer tests: prompt rendering, schema validation, prefilter.
LLM calls themselves are not made here (see test_pipeline_e2e for the live path)."""

import pytest
from pydantic import ValidationError

from app.judging.judge import _compact_matrix, _render_prompt, _title_norm
from app.core.classify import load_targeting
from app.judging.prefilter import should_prefilter
from app.judging.schema import EmployeeVerdict, JudgeResponse

SYSTEM_TEMPLATE = "Matrix:\n{{TARGETING_MATRIX}}\nIndustries: {{ICP_SUMMARY}}"


def test_render_prompt_injects_matrix():
    rendered = _render_prompt(SYSTEM_TEMPLATE)
    assert "{{TARGETING_MATRIX}}" not in rendered
    assert "End User (Plant / Facility Owner)" in rendered
    assert "Oil & Gas" in rendered


def test_compact_matrix_is_smaller_than_json_and_lossless():
    """The Cerebras free-tier path (8K context cap) uses this instead of the
    full JSON dump — must be meaningfully smaller but keep every designation."""
    import json
    targeting = load_targeting()
    compact = _compact_matrix(targeting)
    full_json = json.dumps(targeting, indent=1, ensure_ascii=False)
    assert len(compact) < len(full_json) * 0.85
    assert "Reliability Engineer" in compact
    for customer_type in targeting:
        assert customer_type in compact


def test_render_prompt_compact_mode_uses_compact_matrix():
    rendered = _render_prompt(SYSTEM_TEMPLATE, compact=True)
    assert '"' not in rendered.split("Industries:")[0]  # no JSON punctuation
    assert "Reliability Engineer" in rendered


def test_title_norm():
    assert _title_norm("  Senior   Reliability Engineer ") == "senior reliability engineer"
    assert _title_norm(None) == ""


def test_schema_accepts_valid_verdict():
    r = JudgeResponse(verdicts=[EmployeeVerdict(
        employee_ref="abc", verdict="enrich", confidence=0.92,
        matched_designation="Reliability Engineer",
        function_group="Engineering & Reliability", reasoning="direct match")])
    assert r.verdicts[0].verdict == "enrich"


def test_schema_rejects_bad_verdict():
    with pytest.raises(ValidationError):
        EmployeeVerdict(employee_ref="abc", verdict="maybe", confidence=0.5)
    with pytest.raises(ValidationError):
        EmployeeVerdict(employee_ref="abc", verdict="skip", confidence=1.5)


def test_prefilter_off_by_default():
    assert should_prefilter("Marketing Intern", []) is False


def test_prefilter_matches_when_enabled():
    assert should_prefilter("Marketing Intern", ["intern"]) is True
    assert should_prefilter("Plant Manager", ["intern"]) is False
