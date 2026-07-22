"""Structured-output contract for the judge. A data shape only — no decision
logic lives here or in judge.py; the system prompt carries all judgment."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class EmployeeVerdict(BaseModel):
    employee_ref: str = Field(description="The 'ref' id of the employee being judged, echoed back")
    verdict: Literal["enrich", "skip", "unsure"]
    confidence: float = Field(ge=0.0, le=1.0)
    matched_designation: Optional[str] = None
    function_group: Optional[str] = None
    reasoning: str = ""


class JudgeResponse(BaseModel):
    verdicts: List[EmployeeVerdict]
