from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field


class AppSettings(Document):
    """Singleton live-settings document, seeded from settings.yaml on first boot."""
    key: Indexed(str, unique=True) = "app"
    values: dict = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "settings"


class Prompt(Document):
    """Versioned judge system prompt. Exactly one active version."""
    version: Indexed(int, unique=True)
    body: str
    active: bool = False
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "prompts"


class VerdictCacheEntry(Document):
    """(normalized title, customer_type, prompt_version) -> verdict.
    The single biggest LLM cost saver — repeated titles skip the judge."""
    title_norm: str
    customer_type: str
    prompt_version: int
    verdict: str
    confidence: float
    matched_designation: Optional[str] = None
    function_group: Optional[str] = None
    reasoning: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "verdict_cache"
        indexes = [
            [("title_norm", pymongo.ASCENDING), ("customer_type", pymongo.ASCENDING),
             ("prompt_version", pymongo.ASCENDING)],
        ]


class CreditLedgerEntry(Document):
    """Every credit spent, attributable to run/company/employee/engine."""
    run_id: PydanticObjectId
    company_id: Optional[PydanticObjectId] = None
    employee_id: Optional[PydanticObjectId] = None
    engine: str
    action: str          # org_enrich | people_match | lusha_search | lusha_enrich
    credits: int = 1
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "credit_ledger"
        indexes = [[("run_id", pymongo.ASCENDING)]]
