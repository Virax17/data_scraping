from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import companies, exports, reveal, runs, settings, uploads
from app.db.session import close_db, init_db
from app.jobs.worker import start_workers, stop_workers

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_workers()
    yield
    await stop_workers()
    await close_db()


app = FastAPI(title="Tritorc Enrichment v3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)
app.include_router(runs.router)
app.include_router(companies.router)
app.include_router(reveal.router)
app.include_router(settings.router)
app.include_router(exports.router)


@app.get("/api/health")
async def health():
    return {"ok": True}
