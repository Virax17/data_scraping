"""Queue consumers, started as asyncio tasks at app startup."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from beanie import PydanticObjectId

from app.config import get_config
from app.jobs import pipeline
from app.jobs.queue import Job, get_queue
from app.models.run import Run

log = logging.getLogger(__name__)
_tasks: list[asyncio.Task] = []


async def _handle(job: Job) -> None:
    if job.kind == "process_company":
        await pipeline.process_company(PydanticObjectId(job.payload["company_id"]))
    elif job.kind == "reveal_company":
        await pipeline.reveal_company(PydanticObjectId(job.payload["company_id"]))
    elif job.kind == "finalize_run":
        await _finalize_run(PydanticObjectId(job.payload["run_id"]))
    else:
        log.warning("unknown job kind %s", job.kind)


async def _finalize_run(run_id: PydanticObjectId) -> None:
    run = await Run.get(run_id)
    if run and run.status not in ("failed", "paused"):
        run.status = "awaiting_review" if not run.auto_mode else "done"
        run.updated_at = datetime.now(timezone.utc)
        await run.save()


async def _worker_loop(name: str) -> None:
    queue = get_queue()
    while True:
        job = await queue.get()
        try:
            await _handle(job)
        except Exception:  # noqa: BLE001
            log.exception("worker %s: job %s failed", name, job.kind)
        finally:
            queue.task_done()


def start_workers() -> None:
    n = get_config().worker_concurrency
    for i in range(n):
        _tasks.append(asyncio.create_task(_worker_loop(f"w{i}")))
    log.info("started %d pipeline workers", n)


async def stop_workers() -> None:
    for t in _tasks:
        t.cancel()
