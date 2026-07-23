"""Run listing, detail, and SSE progress stream."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_config
from app.models.company import Company
from app.models.employee import Employee
from app.models.run import Run

router = APIRouter(prefix="/api/runs", tags=["runs"])

STOPPABLE_STATUSES = {
    "queued", "resolving", "sweeping", "judging", "awaiting_review", "revealing",
}


async def _resolution_stats(run_id: PydanticObjectId) -> dict:
    """companies_found/not_found + how many resolved via each engine. A
    company can count toward both apollo_used and lusha_used when Apollo
    matched the org but Lusha had to supply the domain (resolution_source
    "apollo_name+lusha_domain") — both engines genuinely contributed."""
    companies = await Company.find(Company.run_id == run_id).to_list()
    found = sum(1 for c in companies if c.resolution_source)
    apollo_used = sum(1 for c in companies if c.resolution_source and "apollo" in c.resolution_source)
    lusha_used = sum(1 for c in companies if c.resolution_source and "lusha" in c.resolution_source)
    return {
        "companies_found": found,
        "companies_not_found": len(companies) - found,
        "apollo_used": apollo_used,
        "lusha_used": lusha_used,
    }


async def _run_dict(run: Run) -> dict:
    d = run.model_dump(mode="json", exclude={"settings_snapshot"})
    d["id"] = str(run.id)
    d["stats"] = await _resolution_stats(run.id)
    return d


@router.get("")
async def list_runs(limit: int = 50):
    runs = await Run.find_all().sort(-Run.created_at).limit(limit).to_list()
    return [await _run_dict(r) for r in runs]


@router.get("/{run_id}")
async def get_run(run_id: PydanticObjectId):
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)
    return await _run_dict(run)


@router.post("/{run_id}/stop")
async def stop_run(run_id: PydanticObjectId):
    """Cooperative stop: marks the run so every in-flight/queued company job
    bails at its next checkpoint (see pipeline._bail_if_stopped) instead of
    continuing to spend Apollo/Lusha credits or LLM tokens."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)
    if run.status not in STOPPABLE_STATUSES:
        raise HTTPException(422, f"run is already {run.status}, nothing to stop")
    run.status = "stopped"
    run.error = "stopped by user"
    await run.save()
    return await _run_dict(run)


@router.delete("/{run_id}")
async def delete_run(run_id: PydanticObjectId):
    """Permanently deletes the run, every company/employee doc under it, and
    its exported Excel files. Does not touch the global contact_store —
    already-revealed contacts stay free to reuse in future runs."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)

    company_ids = [c.id for c in await Company.find(Company.run_id == run_id).to_list()]
    if company_ids:
        await Employee.find({"company_id": {"$in": company_ids}}).delete()
    await Company.find(Company.run_id == run_id).delete()

    output_dir = Path(get_config().output_dir)
    for path in output_dir.glob(f"{run_id}*.xlsx"):
        path.unlink(missing_ok=True)

    await run.delete()
    return {"deleted": True}


@router.get("/{run_id}/companies")
async def run_companies(run_id: PydanticObjectId, skip: int = 0, limit: int = 100):
    companies = await (Company.find(Company.run_id == run_id)
                       .skip(skip).limit(limit).to_list())
    out = []
    for c in companies:
        d = c.model_dump(mode="json", exclude={"org", "classification"})
        d["id"] = str(c.id)
        d["industry"] = (c.org or {}).get("industry")
        d["org_employees"] = (c.org or {}).get("estimated_num_employees")
        out.append(d)
    return out


@router.get("/{run_id}/events")
async def run_events(run_id: PydanticObjectId):
    """SSE: emits the run doc every 2s until it reaches a terminal state."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)

    async def stream():
        terminal = {"done", "failed", "stopped"}
        while True:
            run = await Run.get(run_id)
            if run is None:
                break
            yield f"data: {json.dumps(await _run_dict(run))}\n\n"
            if run.status in terminal:
                break
            await asyncio.sleep(2)

    return StreamingResponse(stream(), media_type="text/event-stream")
