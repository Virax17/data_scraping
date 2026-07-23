from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from beanie import Document
from pydantic import Field

RunStatus = Literal[
    "queued", "resolving", "sweeping", "judging",
    "awaiting_review", "revealing", "done", "failed", "paused", "stopped",
]


class Run(Document):
    filename: str
    status: RunStatus = "queued"
    auto_mode: bool = True
    settings_snapshot: dict = Field(default_factory=dict)
    search_options: dict = Field(default_factory=dict)
    prompt_version: int | None = None

    companies_total: int = 0
    companies_done: int = 0
    employees_found: int = 0
    employees_judged: int = 0
    employees_approved: int = 0
    employees_revealed: int = 0
    credits_spent: int = 0

    export_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "runs"
