"""POST an Excel/CSV of companies -> create a run and enqueue every company."""

from __future__ import annotations

import io
import json

import openpyxl
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_live_settings
from app.core.dedup import domain_from_website
from app.jobs.queue import enqueue
from app.judging.judge import ensure_active_prompt
from app.models.company import Company
from app.models.run import Run

router = APIRouter(prefix="/api/runs", tags=["uploads"])


def _parse_rows(filename: str, content: bytes) -> list[dict]:
    """Extract {name, website, country, city} rows. Auto-detects columns by
    header; country/city are optional per-row region overrides."""
    rows: list[dict] = []
    if filename.lower().endswith(".csv"):
        import csv
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        raw = list(reader)
        if not raw:
            return []
        headers = {h.lower().strip(): h for h in raw[0].keys()}
    else:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        ws = wb.active
        data = list(ws.iter_rows(values_only=True))
        if not data:
            return []
        header_row = [str(h).strip() if h else "" for h in data[0]]
        headers = {h.lower(): h for h in header_row}
        raw = [dict(zip(header_row, r)) for r in data[1:]]

    name_col = next((headers[h] for h in headers
                     if "name" in h or "company" in h), None)
    web_col = next((headers[h] for h in headers
                    if "website" in h or "domain" in h or "url" in h), None)
    country_col = next((headers[h] for h in headers
                        if "country" in h or "region" in h), None)
    city_col = next((headers[h] for h in headers if "city" in h), None)
    if not name_col:
        raise HTTPException(422, "could not find a company-name column")

    for r in raw:
        name = str(r.get(name_col) or "").strip()
        website = str(r.get(web_col) or "").strip() if web_col else ""
        country = str(r.get(country_col) or "").strip() if country_col else ""
        city = str(r.get(city_col) or "").strip() if city_col else ""
        if name:
            rows.append({"name": name, "website": website or None,
                        "country": country or None, "city": city or None})
    return rows


@router.post("", status_code=201)
async def create_run(file: UploadFile = File(...),
                     auto_mode: bool | None = Form(None),
                     country: str | None = Form(None),
                     city: str | None = Form(None),
                     search_options: str | None = Form(None)):
    content = await file.read()
    rows = _parse_rows(file.filename or "input.xlsx", content)
    if not rows:
        raise HTTPException(422, "no company rows found in file")

    settings = await get_live_settings()
    try:
        form_options = json.loads(search_options) if search_options else {}
    except json.JSONDecodeError:
        raise HTTPException(422, "search_options must be valid JSON")
    options = {**(settings.get("search_defaults") or {}), **form_options}
    if country:
        options["country"] = country
    if city:
        options["city"] = city

    prompt = await ensure_active_prompt()
    run = Run(
        filename=file.filename or "input.xlsx",
        auto_mode=settings.get("auto_mode", True) if auto_mode is None else auto_mode,
        settings_snapshot=settings,
        search_options=options,
        prompt_version=prompt.version,
        status="resolving",
    )
    await run.insert()

    seen_domains: set[str] = set()
    count = 0
    for row in rows:
        domain = domain_from_website(row["website"])
        dedup_key = domain or row["name"].lower()
        if dedup_key in seen_domains:
            continue
        seen_domains.add(dedup_key)
        company = Company(run_id=run.id, input_name=row["name"],
                          website=row["website"], domain=domain,
                          target_country=row["country"] or country or None,
                          target_city=row["city"] or city or None)
        await company.insert()
        await enqueue("process_company", company_id=str(company.id))
        count += 1

    run.companies_total = count
    await run.save()
    return {"run_id": str(run.id), "companies": count}
