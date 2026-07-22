"""Credit estimate + confirm-reveal (the budget gate)."""

from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException

from app.config import get_live_settings
from app.core.budget import estimate_credits
from app.jobs.queue import enqueue
from app.models.company import Company
from app.models.employee import Employee
from app.models.run import Run

router = APIRouter(prefix="/api/runs", tags=["reveal"])


async def _approved_count(run_id: PydanticObjectId) -> int:
    employees = await Employee.find(Employee.run_id == run_id).to_list()
    return sum(1 for e in employees
               if e.effective_approved and e.reveal.status in ("approved", "pending"))


@router.post("/{run_id}/estimate")
async def estimate(run_id: PydanticObjectId):
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)
    settings = await get_live_settings()
    count = await _approved_count(run_id)
    est = estimate_credits(count, int(settings.get("run_credit_budget", 250)))
    est["approved_contacts"] = count
    est["credits_already_spent"] = run.credits_spent
    return est


@router.post("/{run_id}/reveal")
async def confirm_reveal(run_id: PydanticObjectId, force: bool = False):
    """Start the paid reveal stage for every company awaiting review.
    Over-budget runs require force=true (the user confirmed the estimate)."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)
    settings = await get_live_settings()
    count = await _approved_count(run_id)
    est = estimate_credits(count, int(settings.get("run_credit_budget", 250)))
    if est["over_budget"] and not force:
        raise HTTPException(402, detail=est)

    companies = await Company.find(Company.run_id == run_id,
                                   Company.status == "awaiting_review").to_list()
    for c in companies:
        await enqueue("reveal_company", company_id=str(c.id))
    run.status = "revealing"
    run.error = None
    await run.save()
    await enqueue("finalize_run", run_id=str(run_id))
    return {"queued_companies": len(companies), **est}
