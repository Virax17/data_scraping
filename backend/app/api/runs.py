"""Run listing, detail, and SSE progress stream."""

from __future__ import annotations

import asyncio
import json

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.company import Company
from app.models.run import Run

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _run_dict(run: Run) -> dict:
    d = run.model_dump(mode="json", exclude={"settings_snapshot"})
    d["id"] = str(run.id)
    return d


@router.get("")
async def list_runs(limit: int = 50):
    runs = await Run.find_all().sort(-Run.created_at).limit(limit).to_list()
    return [_run_dict(r) for r in runs]


@router.get("/{run_id}")
async def get_run(run_id: PydanticObjectId):
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)
    return _run_dict(run)


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
        terminal = {"done", "failed"}
        while True:
            run = await Run.get(run_id)
            if run is None:
                break
            yield f"data: {json.dumps(_run_dict(run))}\n\n"
            if run.status in terminal:
                break
            await asyncio.sleep(2)

    return StreamingResponse(stream(), media_type="text/event-stream")
