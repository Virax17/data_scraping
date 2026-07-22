"""Live settings + prompt versioning endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import default_settings, get_live_settings
from app.judging.judge import ensure_active_prompt
from app.models.misc import AppSettings, Prompt

router = APIRouter(prefix="/api", tags=["settings"])

# Keys the UI may edit — anything else in a PUT is rejected.
EDITABLE_KEYS = set(default_settings().keys())


@router.get("/settings")
async def get_settings():
    return await get_live_settings()


@router.put("/settings")
async def put_settings(values: dict):
    unknown = set(values) - EDITABLE_KEYS
    if unknown:
        raise HTTPException(422, f"unknown settings keys: {sorted(unknown)}")
    doc = await AppSettings.find_one(AppSettings.key == "app")
    if doc is None:
        doc = AppSettings(key="app", values={})
    doc.values.update(values)
    doc.updated_at = datetime.now(timezone.utc)
    await doc.save()
    return await get_live_settings()


# ------------------------------------------------------------------- prompts

@router.get("/prompts")
async def list_prompts():
    await ensure_active_prompt()
    prompts = await Prompt.find_all().sort(-Prompt.version).to_list()
    return [{"version": p.version, "active": p.active,
             "created_by": p.created_by, "created_at": p.created_at.isoformat(),
             "body": p.body} for p in prompts]


class NewPromptBody(BaseModel):
    body: str
    created_by: str = "user"
    activate: bool = True


@router.post("/prompts", status_code=201)
async def save_prompt(payload: NewPromptBody):
    latest = await Prompt.find_all().sort(-Prompt.version).first_or_none()
    version = (latest.version + 1) if latest else 1
    prompt = Prompt(version=version, body=payload.body,
                    created_by=payload.created_by, active=False)
    await prompt.insert()
    if payload.activate:
        await _activate(version)
    return {"version": version, "active": payload.activate}


@router.post("/prompts/{version}/activate")
async def activate_prompt(version: int):
    await _activate(version)
    return {"active_version": version}


async def _activate(version: int) -> None:
    target = await Prompt.find_one(Prompt.version == version)
    if not target:
        raise HTTPException(404, f"prompt v{version} not found")
    async for p in Prompt.find(Prompt.active == True):  # noqa: E712
        p.active = False
        await p.save()
    target.active = True
    await target.save()
