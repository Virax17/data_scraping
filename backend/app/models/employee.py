from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field

VerdictValue = Literal["enrich", "skip", "unsure"]
RevealStatus = Literal["pending", "approved", "rejected", "revealed", "failed", "cached"]


class Verdict(BaseModel):
    verdict: VerdictValue
    confidence: float = 0.0
    matched_designation: Optional[str] = None
    function_group: Optional[str] = None
    reasoning: str = ""
    prompt_version: int | None = None
    from_cache: bool = False


class Review(BaseModel):
    approved: Optional[bool] = None      # None = untouched; True/False = human decision
    overridden_by: Optional[str] = None
    overridden_at: Optional[datetime] = None


class Reveal(BaseModel):
    status: RevealStatus = "pending"
    email: Optional[str] = None
    email_status: Optional[str] = None
    engine: Optional[str] = None         # apollo | lusha | contact_store
    credits: int = 0
    revealed_at: Optional[datetime] = None


class Employee(Document):
    run_id: Indexed(PydanticObjectId)
    company_id: Indexed(PydanticObjectId)

    # Search preview fields (free)
    apollo_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None       # obfuscated until reveal
    full_name: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    linkedin_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    has_email: Optional[bool] = None
    raw_preview: dict = Field(default_factory=dict)

    verdict: Optional[Verdict] = None
    review: Review = Field(default_factory=Review)
    reveal: Reveal = Field(default_factory=Reveal)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "employees"
        indexes = [
            [("run_id", pymongo.ASCENDING), ("verdict.verdict", pymongo.ASCENDING)],
            [("company_id", pymongo.ASCENDING)],
        ]

    @property
    def effective_approved(self) -> bool:
        """Human override wins; otherwise the LLM verdict + auto threshold decided
        at gate time (stored in reveal.status)."""
        if self.review.approved is not None:
            return self.review.approved
        return self.reveal.status == "approved"
