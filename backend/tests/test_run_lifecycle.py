"""Stop and delete a run: cooperative cancellation checkpoints in the
pipeline, and full cleanup (companies, employees, export files) on delete."""

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.api.runs import delete_run, stop_run
from app.db.session import ALL_DOCUMENTS
from app.jobs import pipeline
from app.models.company import Company
from app.models.employee import Employee
from app.models.run import Run
from fastapi import HTTPException


@pytest.fixture(autouse=True)
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield


async def test_stop_run_rejects_terminal_run():
    run = Run(filename="t.xlsx", companies_total=1, status="done")
    await run.insert()
    with pytest.raises(HTTPException) as exc:
        await stop_run(run.id)
    assert exc.value.status_code == 422


async def test_stop_run_marks_stopped():
    run = Run(filename="t.xlsx", companies_total=1, status="sweeping")
    await run.insert()
    result = await stop_run(run.id)
    assert result["status"] == "stopped"
    run = await Run.get(run.id)
    assert run.status == "stopped"


async def test_process_company_bails_immediately_when_run_stopped(monkeypatch):
    class FailIfCalled:
        async def organization_enrich(self, *a, **kw):
            raise AssertionError("resolve must not run once the run is stopped")

    monkeypatch.setattr(pipeline, "apollo", lambda: FailIfCalled())

    run = Run(filename="t.xlsx", companies_total=1, status="stopped")
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme", domain="acme.com")
    await company.insert()

    await pipeline.process_company(company.id)

    company = await Company.get(company.id)
    assert company.status == "failed"
    assert "run stopped by user" in company.notes
    run = await Run.get(run.id)
    assert run.companies_done == 1


async def test_process_company_bails_between_stages_when_stopped_mid_flight(monkeypatch):
    class FakeApollo:
        async def organization_search(self, name):
            return {"industry": "oil & gas", "estimated_num_employees": 50,
                    "primary_domain": "acme.com"}

        async def people_search_page(self, *a, **kw):
            raise AssertionError("sweep must not run once the run is stopped mid-flight")

    monkeypatch.setattr(pipeline, "apollo", lambda: FakeApollo())

    run = Run(filename="t.xlsx", companies_total=1, status="resolving")
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme", domain="acme.com")
    await company.insert()

    # Simulate the user hitting Stop while resolve_company is in flight: by
    # the time process_company checks again (after resolve), it must bail.
    real_resolve = pipeline.resolve_company

    async def resolve_then_stop(c):
        result = await real_resolve(c)
        r = await Run.get(run.id)
        r.status = "stopped"
        await r.save()
        return result

    monkeypatch.setattr(pipeline, "resolve_company", resolve_then_stop)

    await pipeline.process_company(company.id)

    company = await Company.get(company.id)
    assert company.status == "failed"
    assert "run stopped by user" in company.notes


async def test_delete_run_removes_companies_employees_and_run():
    run = Run(filename="t.xlsx", companies_total=1)
    await run.insert()
    company = Company(run_id=run.id, input_name="Acme", domain="acme.com")
    await company.insert()
    emp = Employee(run_id=run.id, company_id=company.id, apollo_id="p1", title="Welder")
    await emp.insert()

    result = await delete_run(run.id)

    assert result == {"deleted": True}
    assert await Run.get(run.id) is None
    assert await Company.get(company.id) is None
    assert await Employee.get(emp.id) is None


async def test_delete_run_404_for_missing_run():
    from beanie import PydanticObjectId
    with pytest.raises(HTTPException) as exc:
        await delete_run(PydanticObjectId())
    assert exc.value.status_code == 404
