from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from beanie import Document, Indexed
from pydantic import Field


class ContactStoreEntry(Document):
    """Global idempotency store — every contact ever revealed, across all runs.
    Keyed by domain + (apollo id or LinkedIn URL). Never pay twice."""

    key: Indexed(str, unique=True)
    domain: Optional[str] = None
    email: Optional[str] = None
    engine: str = "apollo"
    revealed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "contact_store"
