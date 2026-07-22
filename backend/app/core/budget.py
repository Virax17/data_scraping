"""Credit estimation + global idempotency checks (Mongo-backed contact_store)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.contact_store import ContactStoreEntry


def estimate_credits(approved_count: int, budget: int, credits_per_reveal: int = 1) -> dict:
    estimated = approved_count * credits_per_reveal
    return {
        "estimated_credits": estimated,
        "budget": budget,
        "over_budget": estimated > budget,
    }


def contact_key(domain: str | None, apollo_id: str | None, linkedin_url: str | None) -> str:
    return f"{(domain or '').lower()}::{(apollo_id or linkedin_url or '').lower()}"


async def already_revealed(domain: str | None, apollo_id: str | None,
                           linkedin_url: str | None,
                           freshness_days: int | None = None) -> ContactStoreEntry | None:
    """Return the stored entry if this contact was revealed before (optionally
    within a freshness window), else None. Never pay twice for one person."""
    entry = await ContactStoreEntry.find_one(
        ContactStoreEntry.key == contact_key(domain, apollo_id, linkedin_url)
    )
    if entry is None:
        return None
    if freshness_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)
        revealed_at = entry.revealed_at
        if revealed_at.tzinfo is None:
            revealed_at = revealed_at.replace(tzinfo=timezone.utc)
        if revealed_at < cutoff:
            return None
    return entry


async def mark_revealed(domain: str | None, apollo_id: str | None,
                        linkedin_url: str | None, email: str | None,
                        engine: str) -> None:
    key = contact_key(domain, apollo_id, linkedin_url)
    existing = await ContactStoreEntry.find_one(ContactStoreEntry.key == key)
    if existing:
        existing.email = email or existing.email
        existing.engine = engine
        existing.revealed_at = datetime.now(timezone.utc)
        await existing.save()
    else:
        await ContactStoreEntry(
            key=key, domain=domain, email=email, engine=engine,
            revealed_at=datetime.now(timezone.utc),
        ).insert()
