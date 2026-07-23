"""Run detail stats: companies found/not found, per-engine usage counts."""

import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.api.runs import get_run
from app.db.session import ALL_DOCUMENTS
from app.models.company import Company
from app.models.run import Run


@pytest.fixture(autouse=True)
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield


async def test_run_stats_breakdown_by_engine():
    run = Run(filename="t.xlsx", companies_total=5)
    await run.insert()
    specs = [
        ("apollo_domain", "apollo_domain"),
        ("apollo_name", "apollo_name"),
        ("lusha", "lusha"),
        ("apollo_name+lusha_domain", "apollo_name+lusha_domain"),
        (None, None),
    ]
    for name, source in specs:
        c = Company(run_id=run.id, input_name=name or "unresolved", resolution_source=source)
        await c.insert()

    result = await get_run(run.id)

    assert result["stats"] == {
        "companies_found": 4,
        "companies_not_found": 1,
        "apollo_used": 3,   # apollo_domain, apollo_name, apollo_name+lusha_domain
        "lusha_used": 2,    # lusha, apollo_name+lusha_domain
    }


async def test_run_stats_all_unresolved():
    run = Run(filename="t.xlsx", companies_total=2)
    await run.insert()
    await Company(run_id=run.id, input_name="A", resolution_source=None).insert()
    await Company(run_id=run.id, input_name="B", resolution_source=None).insert()

    result = await get_run(run.id)

    assert result["stats"] == {
        "companies_found": 0,
        "companies_not_found": 2,
        "apollo_used": 0,
        "lusha_used": 0,
    }
