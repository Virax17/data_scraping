"""Contact dedup: LinkedIn URL -> email -> Apollo id -> name+company. First
wins; later duplicates append their company to a _dedup_companies note on the
kept row.

Apollo id sits ahead of name+company because Apollo's free preview never
returns a real full_name (only first_name + an obfuscated last name) — every
unrevealed person at a company would otherwise share the same
("", company) key and collapse into a single row."""

from __future__ import annotations

from urllib.parse import urlparse


def domain_from_website(website: str | None) -> str | None:
    if not website:
        return None
    website = website.strip()
    if not website:
        return None
    if "://" not in website:
        website = "https://" + website
    host = urlparse(website).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _dedup_key(contact: dict) -> tuple:
    linkedin = (contact.get("linkedin_url") or "").strip().lower()
    if linkedin:
        return ("linkedin", linkedin)
    email = (contact.get("email") or "").strip().lower()
    if email:
        return ("email", email)
    apollo_id = (contact.get("apollo_id") or "").strip()
    if apollo_id:
        return ("apollo_id", apollo_id)
    name = (contact.get("full_name") or "").strip().lower()
    company = (contact.get("company_name") or "").strip().lower()
    return ("name_company", name, company)


def dedup_contacts(contacts: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    order: list[tuple] = []
    for contact in contacts:
        key = _dedup_key(contact)
        if key in seen:
            existing = seen[key]
            companies = existing.setdefault(
                "_dedup_companies", [existing.get("company_name")]
            )
            other = contact.get("company_name")
            if other and other not in companies:
                companies.append(other)
        else:
            seen[key] = dict(contact)
            order.append(key)
    return [seen[k] for k in order]
