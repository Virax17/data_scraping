"""In-process async job queue. One job = one (kind, payload) tuple.
Workers are started at app startup (see worker.py). For a small internal
team this beats a Redis/Celery dependency; swap later if scale demands."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class Job:
    kind: str            # "process_company" | "reveal_company" | "finalize_run"
    payload: dict = field(default_factory=dict)


_queue: asyncio.Queue[Job] = asyncio.Queue()


def get_queue() -> asyncio.Queue[Job]:
    return _queue


async def enqueue(kind: str, **payload) -> None:
    await _queue.put(Job(kind=kind, payload=payload))
