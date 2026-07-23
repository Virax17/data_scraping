"""End-to-end smoke test against an in-memory Mongo (mongomock-motor).
Provider + LLM calls are monkeypatched with fixtures — zero credits, no network."""

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.db.session import ALL_DOCUMENTS
from app.jobs import pipeline
from app.models.company import Company
from app.models.employee import Employee, Verdict
from app.models.run import Run


@pytest.fixture(autouse=True)
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield


class FakeApollo:
    async def organization_enrich(self, domain=None, name=None):
        return {"industry": "oil & gas", "estimated_num_employees": 300,
                "primary_domain": domain, "short_description": "refinery operator"}

    async def people_search_page(self, domain, page=1, per_page=100, seniorities=None,
                                 person_locations=None, organization_locations=None,
                                 person_titles=None, q_keywords=None,
                                 organization_num_employees_ranges=None):
        if page > 1:
            return {"people": [], "total_entries": 2}
        return {"people": [
            {"id": "p1", "first_name": "Jane", "name": "Jane D.",
             "title": "Reliability Engineer", "has_email": True},
            {"id": "p2", "first_name": "Bob", "name": "Bob S.",
             "title": "Marketing Intern", "has_email": False},
        ], "total_entries": 2}

    async def people_bulk_match(self, ids):
        return {"matches": [{"id": "p1", "first_name": "Jane", "last_name": "Doe",
                             "email": "jane@acme.com", "email_status": "verified"}],
                "credits_consumed": len(ids)}


async def fake_judge(company, employees):
    judged = 0
    for e in employees:
        if e.verdict:
            continue
        is_target = "engineer" in (e.title or "").lower()
        e.verdict = Verdict(verdict="enrich" if is_target else "skip",
                            confidence=0.95 if is_target else 0.9,
                            reasoning="fixture")
        await e.save()
        judged += 1
    return judged


async def test_full_company_pipeline(monkeypatch):
    fake = FakeApollo()
    monkeypatch.setattr(pipeline, "apollo", lambda: fake)
    monkeypatch.setattr(pipeline, "judge_company", fake_judge)

    run = Run(filename="t.xlsx", companies_total=1, auto_mode=False)
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme Refinery",
                      website="https://acme.com", domain="acme.com")
    await company.insert()

    await pipeline.process_company(company.id)

    company = await Company.get(company.id)
    assert company.status == "awaiting_review"
    assert company.customer_type == "End User (Plant / Facility Owner)"
    assert company.size_tier == "mid"
    assert company.employees_found == 2
    assert company.employees_approved == 1  # only the engineer

    await pipeline.reveal_company(company.id)
    company = await Company.get(company.id)
    assert company.status == "done"
    assert company.employees_revealed == 1

    jane = await Employee.find_one(Employee.apollo_id == "p1")
    assert jane.reveal.email == "jane@acme.com"
    assert jane.reveal.engine == "apollo"

    # Idempotency: a second run must not re-pay for Jane
    run2 = Run(filename="t2.xlsx", companies_total=1, auto_mode=False)
    await run2.insert()
    company2 = Company(run_id=run2.id, input_name="Acme Refinery",
                       website="https://acme.com", domain="acme.com")
    await company2.insert()
    await pipeline.process_company(company2.id)
    await pipeline.reveal_company(company2.id)
    jane2 = await Employee.find_one(Employee.apollo_id == "p1",
                                    Employee.company_id == company2.id)
    assert jane2.reveal.engine == "contact_store"
    assert jane2.reveal.credits == 0


class FakeApolloMixedRegions:
    """A sweep that returns people from multiple countries — used to confirm
    the region hard-filter drops everyone outside the target office."""

    async def organization_enrich(self, domain=None, name=None):
        return {"industry": "oil & gas", "estimated_num_employees": 300,
                "primary_domain": domain, "short_description": "refinery operator"}

    async def people_search_page(self, domain, page=1, per_page=100, seniorities=None,
                                 person_locations=None, organization_locations=None,
                                 person_titles=None, q_keywords=None,
                                 organization_num_employees_ranges=None):
        if page > 1:
            return {"people": [], "total_entries": 2}
        return {"people": [
            {"id": "us1", "first_name": "Jane", "name": "Jane D.",
             "title": "Reliability Engineer", "has_email": True,
             "city": "Houston", "state": "Texas", "country": "United States"},
            {"id": "fr1", "first_name": "Marc", "name": "Marc D.",
             "title": "Reliability Engineer", "has_email": True,
             "city": "Paris", "state": None, "country": "France"},
        ], "total_entries": 2}


class FakeApolloMultiPage:
    """Two full pages (100 each) + one partial page (14) — 214 total, no
    pagination object, matching Apollo's real response shape. Regression for
    the bug where sweep_company always quit after page 1."""

    def __init__(self):
        self.pages_requested = []

    async def organization_enrich(self, domain=None, name=None):
        return {"industry": "oil & gas", "estimated_num_employees": 214,
                "primary_domain": domain}

    async def people_search_page(self, domain, page=1, per_page=100, seniorities=None,
                                 person_locations=None, organization_locations=None,
                                 person_titles=None, q_keywords=None,
                                 organization_num_employees_ranges=None):
        self.pages_requested.append(page)
        total = 214
        start = (page - 1) * per_page
        end = min(start + per_page, total)
        people = [{"id": f"p{i}", "title": "Welder"} for i in range(start, end)]
        return {"people": people, "total_entries": total}


async def test_sweep_pages_past_page_one_using_total_entries(monkeypatch):
    fake = FakeApolloMultiPage()
    monkeypatch.setattr(pipeline, "apollo", lambda: fake)

    run = Run(filename="t.xlsx", companies_total=1)
    await run.insert()
    company = Company(run_id=run.id, input_name="BigCo", domain="bigco.com")
    await company.insert()

    stored = await pipeline.sweep_company(company)

    assert stored == 214
    assert fake.pages_requested == [1, 2, 3]
    assert await Employee.find(Employee.company_id == company.id).count() == 214


async def test_sweep_hard_filters_by_target_region(monkeypatch):
    fake = FakeApolloMixedRegions()
    monkeypatch.setattr(pipeline, "apollo", lambda: fake)

    run = Run(filename="t.xlsx", companies_total=1, auto_mode=False,
             search_options={"country": "United States"})
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme Refinery",
                      website="https://acme.com", domain="acme.com",
                      target_country="United States")
    await company.insert()

    await pipeline.resolve_company(company)
    stored = await pipeline.sweep_company(company)

    assert stored == 1
    only = await Employee.find(Employee.company_id == company.id).to_list()
    assert len(only) == 1
    assert only[0].apollo_id == "us1"
    assert only[0].country == "United States"


async def test_sweep_no_region_keeps_everyone(monkeypatch):
    fake = FakeApolloMixedRegions()
    monkeypatch.setattr(pipeline, "apollo", lambda: fake)

    run = Run(filename="t.xlsx", companies_total=1, auto_mode=False)
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme Refinery",
                      website="https://acme.com", domain="acme.com")
    await company.insert()

    await pipeline.resolve_company(company)
    stored = await pipeline.sweep_company(company)

    assert stored == 2


class FakeApolloNameOnlyNoDomain:
    """Mimics Apollo's org-by-name search returning a match with no usable
    domain field — the exact shape that used to strand a company with
    domain=None forever."""

    async def organization_search(self, name):
        return {"name": name, "industry": "oil & gas",
                "estimated_num_employees": 50}
        # note: no "primary_domain" or "domain" key


class FakeLushaDomainFallback:
    def __init__(self, domain="acme-recovered.com"):
        self.domain = domain
        self.calls = []

    async def company_search_enrich(self, domain=None, name=None):
        self.calls.append({"domain": domain, "name": name})
        return {"domain": self.domain, "estimated_num_employees": 50}


async def test_resolve_falls_back_to_lusha_for_missing_domain(monkeypatch):
    monkeypatch.setattr(pipeline, "apollo", lambda: FakeApolloNameOnlyNoDomain())
    fake_lusha = FakeLushaDomainFallback()
    monkeypatch.setattr(pipeline, "lusha", lambda: fake_lusha)

    run = Run(filename="t.xlsx", companies_total=1)
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme Refinery", domain=None)
    await company.insert()

    resolved = await pipeline.resolve_company(company)

    assert resolved is True
    assert company.domain == "acme-recovered.com"
    assert company.resolution_source == "apollo_name+lusha_domain"
    assert fake_lusha.calls == [{"domain": None, "name": "Acme Refinery"}]


async def test_resolve_no_domain_fallback_when_lusha_disabled(monkeypatch):
    monkeypatch.setattr(pipeline, "apollo", lambda: FakeApolloNameOnlyNoDomain())
    fake_lusha = FakeLushaDomainFallback()
    monkeypatch.setattr(pipeline, "lusha", lambda: fake_lusha)

    from app.models.misc import AppSettings
    await AppSettings(key="app", values={"lusha_fallback": False}).insert()

    run = Run(filename="t.xlsx", companies_total=1)
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme Refinery", domain=None)
    await company.insert()

    resolved = await pipeline.resolve_company(company)

    assert resolved is True
    assert company.domain is None
    assert fake_lusha.calls == []


async def test_sweep_remark_notes_zero_found(monkeypatch):
    class EmptyApollo:
        async def people_search_page(self, *args, **kwargs):
            return {"people": [], "total_entries": 0}

    monkeypatch.setattr(pipeline, "apollo", lambda: EmptyApollo())
    run = Run(filename="t.xlsx", companies_total=1)
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme", domain="acme.com")
    await company.insert()

    stored = await pipeline.sweep_company(company)

    assert stored == 0
    company = await Company.get(company.id)
    assert "0 employees found" in company.notes


async def test_sweep_remark_notes_count_found(monkeypatch):
    fake = FakeApollo()
    monkeypatch.setattr(pipeline, "apollo", lambda: fake)
    run = Run(filename="t.xlsx", companies_total=1)
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme", domain="acme.com")
    await company.insert()

    stored = await pipeline.sweep_company(company)

    assert stored == 2
    company = await Company.get(company.id)
    assert "2 employees found" in company.notes


async def test_sweep_skips_when_no_domain_resolved(monkeypatch):
    # Regression: companies that only resolved via name-match (no domain)
    # used to call Apollo with domain=None, which returned an unscoped result
    # set instead of erroring — identical "employees" leaked onto every
    # domain-less company. Sweep must skip entirely instead.
    class FailIfCalled:
        async def people_search_page(self, *args, **kwargs):
            raise AssertionError("people_search_page must not be called without a domain")

    monkeypatch.setattr(pipeline, "apollo", lambda: FailIfCalled())

    run = Run(filename="t.xlsx", companies_total=1, auto_mode=False)
    await run.insert()
    company = Company(run_id=run.id, input_name="No Domain Co", domain=None)
    await company.insert()

    stored = await pipeline.sweep_company(company)

    assert stored == 0
    company = await Company.get(company.id)
    assert "no domain resolved" in company.notes
