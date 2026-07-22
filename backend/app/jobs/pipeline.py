"""Per-company pipeline: resolve -> classify -> sweep (free) -> judge -> gate.
Reveal is a separate stage (reveal_company) triggered either automatically
(auto mode, within budget) or by the user from the review screen."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from beanie import PydanticObjectId

from app.config import get_live_settings
from app.core.budget import already_revealed, estimate_credits, mark_revealed
from app.core.classify import classify_company
from app.core.size_tier import size_tier
from app.judging.judge import judge_company
from app.judging.prefilter import should_prefilter
from app.models.company import Company
from app.models.employee import Employee, Reveal, Verdict
from app.models.misc import CreditLedgerEntry
from app.models.run import Run
from app.providers.apollo_client import ApolloClient
from app.providers.lusha_client import LushaClient

log = logging.getLogger(__name__)

_apollo: ApolloClient | None = None
_lusha: LushaClient | None = None


def apollo() -> ApolloClient:
    global _apollo
    if _apollo is None:
        _apollo = ApolloClient()
    return _apollo


def lusha() -> LushaClient:
    global _lusha
    if _lusha is None:
        _lusha = LushaClient()
    return _lusha


async def _ledger(run_id, company_id, engine, action, credits=1, employee_id=None):
    await CreditLedgerEntry(run_id=run_id, company_id=company_id,
                            employee_id=employee_id, engine=engine,
                            action=action, credits=credits).insert()
    run = await Run.get(run_id)
    if run:
        run.credits_spent += credits
        run.updated_at = datetime.now(timezone.utc)
        await run.save()
    company = await Company.get(company_id) if company_id else None
    if company:
        company.credits_spent += credits
        await company.save()


# ---------------------------------------------------------------- resolve

async def resolve_company(company: Company) -> bool:
    """Resolution cascade (ported from v0.2): apollo domain -> apollo name ->
    lusha domain/name -> unresolved."""
    company.status = "resolving"
    await company.save()

    org = None
    if company.domain:
        org = await apollo().organization_enrich(domain=company.domain)
        if org:
            company.resolution_source = "apollo_domain"
            await _ledger(company.run_id, company.id, "apollo", "org_enrich")
    if org is None and company.input_name:
        org = await apollo().organization_search(company.input_name)
        if org:
            company.resolution_source = "apollo_name"
    if org is None:
        settings = await get_live_settings()
        if settings.get("lusha_fallback", True):
            org = await lusha().company_search_enrich(domain=company.domain,
                                                      name=company.input_name)
            if org:
                company.resolution_source = "lusha"
                await _ledger(company.run_id, company.id, "lusha", "company_search")

    if org is None:
        company.status = "unresolved"
        company.notes = "resolution cascade exhausted"
        await company.save()
        return False

    company.org = org
    if not company.domain:
        company.domain = org.get("primary_domain") or org.get("domain")
    industry_text = " ".join(str(x) for x in [
        org.get("industry"), org.get("short_description"), org.get("seo_description"),
    ] if x)
    company.classification = classify_company(company.input_name, industry_text)
    company.customer_type = company.classification.get("customer_type")

    settings = await get_live_settings()
    company.size_tier = size_tier(org.get("estimated_num_employees"),
                                  settings.get("size_tier_bounds"))
    await company.save()
    return True


# ---------------------------------------------------------------- sweep

async def sweep_company(company: Company) -> int:
    """Broad people sweep — NO title filter, everyone at the company (free).
    Hard cap per company; beyond the cap, seniority-banded passes make sure
    the most senior people are captured first."""
    company.status = "sweeping"
    await company.save()
    settings = await get_live_settings()
    cap = int(settings.get("sweep_cap_per_company", 600))
    never_send = settings.get("never_send_titles") or []

    seen_ids: set[str] = set()
    stored = 0

    async def _store(person: dict) -> None:
        nonlocal stored
        pid = person.get("id")
        if pid and pid in seen_ids:
            return
        if pid:
            seen_ids.add(pid)
        title = person.get("title")
        emp = Employee(
            run_id=company.run_id, company_id=company.id,
            apollo_id=pid,
            first_name=person.get("first_name"),
            last_name=person.get("last_name") or person.get("last_name_obfuscated"),
            full_name=person.get("name"),
            title=title,
            seniority=person.get("seniority"),
            linkedin_url=person.get("linkedin_url"),
            city=person.get("city"), state=person.get("state"),
            country=person.get("country"),
            has_email=bool(person.get("has_email")),
            raw_preview={k: v for k, v in person.items() if k != "organization"},
        )
        if should_prefilter(title, never_send):
            emp.verdict = Verdict(verdict="skip", confidence=1.0,
                                  reasoning="prefiltered by never_send_titles setting")
        await emp.insert()
        stored += 1

    async def _paginate(seniorities: list[str] | None) -> bool:
        """Returns False when the cap was hit."""
        page = 1
        while stored < cap:
            result = await apollo().people_search_page(
                company.domain, page=page, seniorities=seniorities)
            people = result["people"]
            if not people:
                return True
            for person in people:
                if stored >= cap:
                    return False
                await _store(person)
            pagination = result.get("pagination") or {}
            total_pages = pagination.get("total_pages") or page
            if page >= total_pages:
                return True
            page += 1
        return False

    # First try unfiltered. If the cap cuts it off, restart per seniority band
    # (most senior first) so the cap is spent on the right people.
    org_size = (company.org or {}).get("estimated_num_employees") or 0
    if org_size and org_size > cap:
        for band in settings.get("seniority_bands", []):
            if stored >= cap:
                break
            await _paginate(band)
    else:
        await _paginate(None)

    company.employees_found = stored
    await company.save()
    return stored


# ---------------------------------------------------------------- judge + gate

async def judge_and_gate(company: Company) -> None:
    company.status = "judging"
    await company.save()
    settings = await get_live_settings()

    employees = await Employee.find(Employee.company_id == company.id).to_list()
    judged = await judge_company(company, employees)
    company.employees_judged = judged

    threshold = float(settings.get("auto_approve_confidence", 0.8))
    cap_by_tier = settings.get("reveal_cap_by_size_tier") or {}
    reveal_cap = int(cap_by_tier.get(company.size_tier)
                     if company.size_tier and company.size_tier in cap_by_tier
                     else settings.get("reveal_cap_per_company", 8))

    employees = await Employee.find(Employee.company_id == company.id).to_list()
    candidates = [e for e in employees
                  if e.verdict and e.verdict.verdict == "enrich"
                  and e.verdict.confidence >= threshold]
    # Highest confidence first; Apollo-has-email first within ties.
    candidates.sort(key=lambda e: (e.verdict.confidence, bool(e.has_email)), reverse=True)
    approved = 0
    for e in candidates:
        if approved >= reveal_cap:
            break
        e.reveal.status = "approved"
        await e.save()
        approved += 1
    company.employees_approved = approved
    company.status = "awaiting_review"
    await company.save()

    run = await Run.get(company.run_id)
    if run:
        run.employees_found += company.employees_found
        run.employees_judged += judged
        run.employees_approved += approved
        run.companies_done += 1
        run.updated_at = datetime.now(timezone.utc)
        await run.save()


# ---------------------------------------------------------------- reveal

async def reveal_company(company_id: PydanticObjectId) -> None:
    """Reveal (paid, email-only) every effectively-approved employee of one
    company: idempotency store first, Apollo bulk_match, Lusha per-contact
    fallback for misses."""
    company = await Company.get(company_id)
    if company is None:
        return
    settings = await get_live_settings()
    freshness = int(settings.get("contact_freshness_days", 90))
    company.status = "revealing"
    await company.save()

    employees = await Employee.find(Employee.company_id == company.id).to_list()
    approved = [e for e in employees if e.effective_approved
                and e.reveal.status in ("approved", "pending")]

    # 1) idempotency — anyone already in the global contact store is free
    to_reveal: list[Employee] = []
    for e in approved:
        entry = await already_revealed(company.domain, e.apollo_id, e.linkedin_url, freshness)
        if entry and entry.email:
            e.reveal = Reveal(status="cached", email=entry.email,
                              engine="contact_store", credits=0,
                              revealed_at=datetime.now(timezone.utc))
            await e.save()
        else:
            to_reveal.append(e)

    # 2) Apollo bulk_match in batches of 10
    misses: list[Employee] = []
    for i in range(0, len(to_reveal), 10):
        batch = to_reveal[i:i + 10]
        ids = [e.apollo_id for e in batch if e.apollo_id]
        if not ids:
            misses.extend(batch)
            continue
        result = await apollo().people_bulk_match(ids)
        matches_by_id = {m.get("id"): m for m in result["matches"] if m}
        credits = result.get("credits_consumed") or len(ids)
        await _ledger(company.run_id, company.id, "apollo", "people_match", credits)
        for e in batch:
            m = matches_by_id.get(e.apollo_id)
            email = (m or {}).get("email")
            if m and email and "email_not_unlocked" not in str(email):
                e.first_name = m.get("first_name") or e.first_name
                e.last_name = m.get("last_name") or e.last_name
                e.reveal = Reveal(status="revealed", email=email,
                                  email_status=m.get("email_status"),
                                  engine="apollo", credits=1,
                                  revealed_at=datetime.now(timezone.utc))
                await e.save()
                await mark_revealed(company.domain, e.apollo_id, e.linkedin_url,
                                    email, "apollo")
            else:
                misses.append(e)

    # 3) Lusha fallback per contact
    if settings.get("lusha_fallback", True):
        for e in misses:
            if not (e.first_name and e.last_name and company.domain):
                e.reveal.status = "failed"
                await e.save()
                continue
            contact = await lusha().contact_search_enrich(
                e.first_name, e.last_name, company.domain)
            email = None
            if contact:
                emails = contact.get("emails") or contact.get("emailAddresses") or []
                if isinstance(emails, list) and emails:
                    first = emails[0]
                    email = first.get("email") if isinstance(first, dict) else first
            await _ledger(company.run_id, company.id, "lusha", "contact_enrich",
                          2, employee_id=e.id)  # search + reveal both billed
            if email:
                e.reveal = Reveal(status="revealed", email=email, engine="lusha",
                                  credits=2, revealed_at=datetime.now(timezone.utc))
                await e.save()
                await mark_revealed(company.domain, e.apollo_id, e.linkedin_url,
                                    email, "lusha")
            else:
                e.reveal.status = "failed"
                await e.save()
    else:
        for e in misses:
            e.reveal.status = "failed"
            await e.save()

    revealed = await Employee.find(
        Employee.company_id == company.id,
        Employee.reveal.status == "revealed").count()
    company.employees_revealed = revealed
    company.status = "done"
    await company.save()

    run = await Run.get(company.run_id)
    if run:
        run.employees_revealed += revealed
        run.updated_at = datetime.now(timezone.utc)
        await run.save()


# ---------------------------------------------------------------- orchestration

async def process_company(company_id: PydanticObjectId) -> None:
    company = await Company.get(company_id)
    if company is None:
        return
    try:
        if not await resolve_company(company):
            run = await Run.get(company.run_id)
            if run:
                run.companies_done += 1
                await run.save()
            return
        await sweep_company(company)
        await judge_and_gate(company)

        run = await Run.get(company.run_id)
        settings = await get_live_settings()
        if run and run.auto_mode:
            est = estimate_credits(run.employees_approved,
                                   int(settings.get("run_credit_budget", 250)))
            if not est["over_budget"]:
                from app.jobs.queue import enqueue
                await enqueue("reveal_company", company_id=str(company.id))
            else:
                run.status = "paused"
                run.error = (f"estimated {est['estimated_credits']} credits exceeds "
                             f"budget {est['budget']} — confirm to proceed")
                await run.save()
    except Exception as exc:  # noqa: BLE001
        log.exception("company %s failed", company_id)
        company.status = "failed"
        company.notes = str(exc)[:500]
        await company.save()
        run = await Run.get(company.run_id)
        if run:
            run.companies_done += 1
            await run.save()
