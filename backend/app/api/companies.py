"""Per-company employee list (review table) + manual overrides."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.employee import Employee

router = APIRouter(prefix="/api", tags=["companies"])


@router.get("/companies/{company_id}/employees")
async def company_employees(company_id: PydanticObjectId,
                            verdict: Optional[str] = None):
    query = Employee.find(Employee.company_id == company_id)
    employees = await query.to_list()
    out = []
    for e in employees:
        if verdict and (e.verdict is None or e.verdict.verdict != verdict):
            continue
        d = e.model_dump(mode="json", exclude={"raw_preview"})
        d["id"] = str(e.id)
        d["effective_approved"] = e.effective_approved
        out.append(d)
    return out


class OverrideBody(BaseModel):
    approved: bool
    by: str = "user"


@router.patch("/employees/{employee_id}")
async def override_employee(employee_id: PydanticObjectId, body: OverrideBody):
    emp = await Employee.get(employee_id)
    if not emp:
        raise HTTPException(404)
    if emp.reveal.status in ("revealed", "cached"):
        raise HTTPException(409, "already revealed — override has no effect")
    emp.review.approved = body.approved
    emp.review.overridden_by = body.by
    emp.review.overridden_at = datetime.now(timezone.utc)
    emp.reveal.status = "approved" if body.approved else "rejected"
    await emp.save()
    return {"ok": True, "effective_approved": emp.effective_approved}


class BulkBody(BaseModel):
    company_id: str
    action: Literal["approve_above", "skip_below"]
    threshold: float
    by: str = "user"


@router.post("/employees/bulk")
async def bulk_override(body: BulkBody):
    employees = await Employee.find(
        Employee.company_id == PydanticObjectId(body.company_id)).to_list()
    changed = 0
    now = datetime.now(timezone.utc)
    for e in employees:
        if e.verdict is None or e.reveal.status in ("revealed", "cached"):
            continue
        conf = e.verdict.confidence
        if body.action == "approve_above" and conf >= body.threshold:
            e.review.approved = True
            e.reveal.status = "approved"
        elif body.action == "skip_below" and conf < body.threshold:
            e.review.approved = False
            e.reveal.status = "rejected"
        else:
            continue
        e.review.overridden_by = body.by
        e.review.overridden_at = now
        await e.save()
        changed += 1
    return {"changed": changed}
