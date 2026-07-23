"""Judge-layer tests: prompt rendering, schema validation, prefilter.
LLM calls themselves are not made here except via a mocked CerebrasClient
(see test_pipeline_e2e for the full pipeline path with judge_company faked out)."""

import pytest
from beanie import PydanticObjectId, init_beanie
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

from app.db.session import ALL_DOCUMENTS
from app.judging import judge as judge_module
from app.judging.judge import _compact_matrix, _render_prompt, _title_norm, judge_company
from app.core.classify import load_targeting
from app.judging.prefilter import should_prefilter
from app.judging.schema import EmployeeVerdict, JudgeResponse
from app.models.company import Company
from app.models.employee import Employee


@pytest.fixture(autouse=True)
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield


async def _make_company_and_employees(titles, customer_type="End User (Plant / Facility Owner)"):
    company = Company(run_id=PydanticObjectId(), input_name="Acme", domain="acme.com",
                      customer_type=customer_type)
    await company.insert()
    employees = []
    for title in titles:
        emp = Employee(run_id=company.run_id, company_id=company.id, title=title,
                       full_name=title, has_email=True)
        await emp.insert()
        employees.append(emp)
    return company, employees

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


def test_render_prompt_always_uses_compact_matrix():
    """Both providers now render with the compact matrix — no JSON dump path."""
    rendered = _render_prompt(SYSTEM_TEMPLATE)
    assert '"' not in rendered.split("Industries:")[0]  # no JSON punctuation
    assert "Reliability Engineer" in rendered


def test_end_user_matrix_includes_project_manager():
    targeting = load_targeting()
    end_user = targeting["End User (Plant / Facility Owner)"]
    ops = end_user["Operations & Turnarounds"]
    assert "Project Manager" in ops
    assert "Capital Projects Manager" in ops


def test_title_norm():
    assert _title_norm("  Senior   Reliability Engineer ") == "senior reliability engineer"
    assert _title_norm(None) == ""


def test_schema_accepts_valid_verdict():
    r = JudgeResponse(verdicts=[EmployeeVerdict(
        employee_ref=0, verdict="enrich", confidence=0.92,
        matched_designation="Reliability Engineer",
        function_group="Engineering & Reliability", reasoning="direct match")])
    assert r.verdicts[0].verdict == "enrich"


def test_schema_rejects_bad_verdict():
    with pytest.raises(ValidationError):
        EmployeeVerdict(employee_ref=0, verdict="maybe", confidence=0.5)
    with pytest.raises(ValidationError):
        EmployeeVerdict(employee_ref=0, verdict="skip", confidence=1.5)


def test_schema_truncates_long_reasoning():
    from app.judging.schema import REASONING_MAX_CHARS
    long_reasoning = "x" * 500
    v = EmployeeVerdict(employee_ref=0, verdict="enrich", confidence=0.5,
                        reasoning=long_reasoning)
    assert len(v.reasoning) == REASONING_MAX_CHARS


def test_prefilter_off_by_default():
    assert should_prefilter("Marketing Intern", []) is False


def test_prefilter_matches_when_enabled():
    assert should_prefilter("Marketing Intern", ["intern"]) is True
    assert should_prefilter("Plant Manager", ["intern"]) is False


def _make_fake_cerebras(responses):
    """responses: list of return values (dict or None), one per call, consumed in order."""
    calls = {"n": 0}

    class FakeCerebras:
        async def judge_completion(self, model, system, payload_json):
            i = calls["n"]
            calls["n"] += 1
            return responses[i]

    return FakeCerebras(), calls


async def test_judge_company_retries_once_on_none_then_succeeds(monkeypatch):
    company, employees = await _make_company_and_employees(["Reliability Engineer"])
    good = {"verdicts": [{"employee_ref": 0, "verdict": "enrich", "confidence": 0.9,
                          "matched_designation": None, "function_group": None,
                          "reasoning": "authority"}]}
    fake, calls = _make_fake_cerebras([None, good])
    monkeypatch.setattr(judge_module, "_cerebras_client", lambda: fake)

    judged = await judge_company(company, employees)

    assert judged == 1
    assert calls["n"] == 2  # first attempt failed, second succeeded
    assert employees[0].verdict.verdict == "enrich"


async def test_judge_company_gives_up_after_second_failure(monkeypatch):
    company, employees = await _make_company_and_employees(["Reliability Engineer"])
    fake, calls = _make_fake_cerebras([None, None])
    monkeypatch.setattr(judge_module, "_cerebras_client", lambda: fake)

    judged = await judge_company(company, employees)

    assert judged == 0
    assert calls["n"] == 2
    assert employees[0].verdict is None


async def test_judge_company_logs_warning_on_ref_mismatch(monkeypatch, caplog):
    company, employees = await _make_company_and_employees(
        ["Reliability Engineer", "Plant Manager"])
    # only ref 0 returned — ref 1 silently missing
    partial = {"verdicts": [{"employee_ref": 0, "verdict": "enrich", "confidence": 0.9,
                             "matched_designation": None, "function_group": None,
                             "reasoning": "authority"}]}
    fake, _ = _make_fake_cerebras([partial])
    monkeypatch.setattr(judge_module, "_cerebras_client", lambda: fake)

    with caplog.at_level("WARNING"):
        judged = await judge_company(company, employees)

    assert judged == 1
    assert any("ref mismatch" in r.message for r in caplog.records)


async def test_judge_company_caches_verdicts_for_resolved_customer_type(monkeypatch):
    good = {"verdicts": [{"employee_ref": 0, "verdict": "enrich", "confidence": 0.9,
                          "matched_designation": None, "function_group": None,
                          "reasoning": "authority"}]}
    fake, calls = _make_fake_cerebras([good, good])
    monkeypatch.setattr(judge_module, "_cerebras_client", lambda: fake)

    company_a, employees_a = await _make_company_and_employees(
        ["Plant Manager"], customer_type="End User (Plant / Facility Owner)")
    await judge_company(company_a, employees_a)

    company_b, employees_b = await _make_company_and_employees(
        ["Plant Manager"], customer_type="End User (Plant / Facility Owner)")
    judged_b = await judge_company(company_b, employees_b)

    assert judged_b == 1
    assert employees_b[0].verdict.from_cache is True
    assert calls["n"] == 1  # second company's identical title was served from cache


async def test_judge_company_ambiguous_customer_type_bypasses_cache(monkeypatch):
    # Regression: classify_company() returning None for two DIFFERENT
    # companies must not let one's cached verdict silently leak into the
    # other via the shared "Unknown / Ambiguous" cache key.
    good = {"verdicts": [{"employee_ref": 0, "verdict": "enrich", "confidence": 0.9,
                          "matched_designation": None, "function_group": None,
                          "reasoning": "authority"}]}
    fake, calls = _make_fake_cerebras([good, good])
    monkeypatch.setattr(judge_module, "_cerebras_client", lambda: fake)

    company_a, employees_a = await _make_company_and_employees(
        ["Plant Manager"], customer_type=None)
    await judge_company(company_a, employees_a)

    company_b, employees_b = await _make_company_and_employees(
        ["Plant Manager"], customer_type=None)
    judged_b = await judge_company(company_b, employees_b)

    assert judged_b == 1
    assert employees_b[0].verdict.from_cache is False
    assert calls["n"] == 2  # both ambiguous companies hit the LLM independently
