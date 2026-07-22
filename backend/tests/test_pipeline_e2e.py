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

    async def people_search_page(self, domain, page=1, per_page=100, seniorities=None):
        if page > 1:
            return {"people": [], "pagination": {}}
        return {"people": [
            {"id": "p1", "first_name": "Jane", "name": "Jane D.",
             "title": "Reliability Engineer", "has_email": True},
            {"id": "p2", "first_name": "Bob", "name": "Bob S.",
             "title": "Marketing Intern", "has_email": False},
        ], "pagination": {"total_pages": 1}}

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
