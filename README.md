# Tritorc Enrichment v3

Upload an Excel of companies (name + website) → the pipeline resolves each
company (Apollo → Lusha cascade), pulls **every employee** via Apollo's free
people search, has an **LLM judge** (system-prompt-driven, zero decision logic
in code) decide who's worth enriching, then reveals work emails within a credit
budget — Apollo first, Lusha fallback, global idempotency so no contact is ever
paid for twice.

See `IMPLEMENTATION_PLAN.md` for the full design.

## Layout

```
backend/   FastAPI + Beanie(MongoDB) + Anthropic SDK
  app/core/       deterministic layer (classify, tiers, dedup, budget, excel)
  app/judging/    the LLM judge — system_prompt.md IS the filtering logic
  app/providers/  Apollo + Lusha REST clients (retry, pacing)
  app/jobs/       async queue + per-company pipeline
  app/api/        routes (uploads, runs, review, reveal, settings, export)
frontend/  Next.js (upload, live run dashboard, review table, settings + prompt editor)
```

## Run locally

The database is **MongoDB Atlas** — `MONGO_URI` in `.env` already points at the
existing cluster (credentials from `D:\tritorc\atlas-credentials.env`). No
local Mongo or Docker needed.

```bash
# Backend  (needs APOLLO_API_KEY / LUSHA_API_KEY / ANTHROPIC_API_KEY in .env)
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend
cd ../frontend
npm install
npm run dev                 # http://localhost:3000
```

## Tests

```bash
cd backend
python -m pytest tests/ -v     # includes an offline e2e pipeline test (zero credits, in-memory Mongo)
```

## How filtering works (important)

Who gets enriched is decided by `backend/app/judging/system_prompt.md` — the
targeting matrix from `Designation _ Problems _ Obstacles.xlsx` is injected into
it at runtime. Edit the prompt from **Settings → Judge system prompt** in the UI
(versioned; each run records which version judged it). `judge.py` is a thin
runner: it batches employees, calls Claude with structured output, and caches
verdicts per (title, customer type, prompt version) so repeated titles cost
zero tokens.

## Credit safety

- People *search* is free — the broad sweep costs nothing.
- Reveal is gated: auto mode reveals only within `run_credit_budget`; anything
  over pauses the run for explicit confirmation.
- Every credit is written to the `credit_ledger` collection.
- The global `contact_store` collection means a contact revealed in any past
  run is reused free (within `contact_freshness_days`).

## Regenerating reference data

If the designation spreadsheet changes:

```bash
cd backend/app/reference_data
python build_reference_data.py
```

## Deployment (later)

Containerization/EC2 was removed for now — local testing only. When ready to
deploy for the team, re-add Dockerfiles + nginx (SSE needs `proxy_buffering off`
on `/api/runs/{id}/events`).
