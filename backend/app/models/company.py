from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field

CompanyStatus = Literal[
    "queued", "resolving", "unresolved", "sweeping", "judging",
    "awaiting_review", "revealing", "done", "failed",
]


class Company(Document):
    run_id: Indexed(PydanticObjectId)
    input_name: str
    website: Optional[str] = None
    domain: Optional[str] = None

    status: CompanyStatus = "queued"
    resolution_source: Optional[str] = None  # apollo_domain | apollo_name | lusha | None
    org: dict = Field(default_factory=dict)  # full resolved payload (industry, employees, ...)
    customer_type: Optional[str] = None
    classification: dict = Field(default_factory=dict)
    size_tier: Optional[str] = None

    employees_found: int = 0
    employees_judged: int = 0
    employees_approved: int = 0
    employees_revealed: int = 0
    credits_spent: int = 0
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "companies"
        indexes = [[("run_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)]]
