"""Structured-output contract for the judge. A data shape only — no decision
logic lives here or in judge.py; the system prompt carries all judgment."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

REASONING_MAX_CHARS = 150


class EmployeeVerdict(BaseModel):
    employee_ref: int = Field(description="The positional index of the employee in the batch, echoed back")
    verdict: Literal["enrich", "skip", "unsure"]
    confidence: float = Field(ge=0.0, le=1.0)
    matched_designation: Optional[str] = None
    function_group: Optional[str] = None
    reasoning: str = ""

    @field_validator("reasoning")
    @classmethod
    def _truncate_reasoning(cls, v: str) -> str:
        return v[:REASONING_MAX_CHARS]


class JudgeResponse(BaseModel):
    verdicts: List[EmployeeVerdict]
