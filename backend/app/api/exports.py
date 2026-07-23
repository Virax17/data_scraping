"""Build + download the enriched .xlsx for a run."""

from __future__ import annotations

from pathlib import Path

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_config
from app.core.dedup import dedup_contacts
from app.core.excel_writer import write_output_excel
from app.models.company import Company
from app.models.employee import Employee
from app.models.run import Run

router = APIRouter(prefix="/api/runs", tags=["exports"])


@router.get("/{run_id}/export")
async def export_run(run_id: PydanticObjectId, include_unrevealed: bool = False,
                     search_only: bool = False):
    """search_only=true dumps every person the free sweep found — any verdict,
    unjudged or prefiltered included — with no email and zero credits spent.
    Lets you sanity-check region/title/keyword targeting before ever
    approving or revealing anyone."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(404)

    companies = await Company.find(Company.run_id == run_id).to_list()
    by_id = {c.id: c for c in companies}
    employees = await Employee.find(Employee.run_id == run_id).to_list()

    contacts = []
    for e in employees:
        revealed = e.reveal.status in ("revealed", "cached")
        if not search_only and not revealed and not (include_unrevealed and e.effective_approved):
            continue
        c = by_id.get(e.company_id)
        org = (c.org if c else {}) or {}
        contacts.append({
            "apollo_id": e.apollo_id,
            "first_name": e.first_name, "last_name": e.last_name,
            "full_name": e.full_name, "title": e.title, "seniority": e.seniority,
            "linkedin_url": e.linkedin_url,
            "city": e.city, "state": e.state, "country": e.country,
            "email": e.reveal.email if revealed else None,
            "email_status": e.reveal.email_status if revealed else None,
            "company_name": c.input_name if c else None,
            "company_domain": c.domain if c else None,
            "website": org.get("website_url"),
            "industry": org.get("industry"),
            "employees": org.get("estimated_num_employees"),
            "annual_revenue": org.get("annual_revenue"),
            "total_funding": org.get("total_funding"),
            "company_phone": org.get("phone"),
            "company_linkedin_url": org.get("linkedin_url"),
            "company_street": org.get("street_address"),
            "company_city": org.get("city"),
            "company_postal_code": org.get("postal_code"),
            "company_state": org.get("state"),
            "company_country": org.get("country"),
            "company_founded_year": org.get("founded_year"),
            "customer_type": c.customer_type if c else None,
            "size_tier": c.size_tier if c else None,
            "verdict": e.verdict.verdict if e.verdict else None,
            "confidence": e.verdict.confidence if e.verdict else None,
            "matched_designation": e.verdict.matched_designation if e.verdict else None,
            "function_group": e.verdict.function_group if e.verdict else None,
            "reasoning": e.verdict.reasoning if e.verdict else None,
            "prompt_version": e.verdict.prompt_version if e.verdict else None,
            "overridden": "yes" if e.review.approved is not None else "",
            "revealed": "yes" if revealed else "no",
            "source": e.reveal.engine if revealed else "search_only (not revealed)",
        })
    contacts = dedup_contacts(contacts)

    run_log = [{
        "company_input_name": c.input_name, "domain": c.domain,
        "resolved": c.status != "unresolved",
        "resolution_source": c.resolution_source,
        "customer_type": c.customer_type, "size_tier": c.size_tier,
        "employees_found": c.employees_found, "judged": c.employees_judged,
        "approved": c.employees_approved, "revealed": c.employees_revealed,
        "credits_spent": c.credits_spent, "status": c.status, "notes": c.notes,
    } for c in companies]

    needs_review = [{
        "company_input_name": c.input_name, "domain": c.domain,
        "reason": c.notes or c.status,
    } for c in companies if c.status in ("unresolved", "failed")]

    suffix = "_search_only" if search_only else ("_with_unrevealed" if include_unrevealed else "")
    out_path = Path(get_config().output_dir) / f"{run_id}{suffix}.xlsx"
    write_output_excel(contacts, run_log, needs_review, out_path)
    if not include_unrevealed and not search_only:
        run.export_path = str(out_path)
        await run.save()

    return FileResponse(out_path, filename=f"tritorc_enriched_{run_id}{suffix}.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
