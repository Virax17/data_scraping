# Tritorc Enrichment v3 — Implementation Plan

**Version:** 1.0 (for review)
**Predecessors:** `DATA/` (P0–P3 scoring library, agent-driven), `tritorc-enrichment/` (v0.2 Node app, title-search-based, JSON-file storage)
**Key references:** `Apollo_Lusha_API_Reference_Tritorc.md` (verified API surface), `Designation _ Problems _ Obstacles.xlsx` (target designation matrix + ICP list)

---

## 1. What changes from v0.2

| Aspect | v0.2 (current app) | v3 (this plan) |
|---|---|---|
| People search | Pre-filtered by `person_titles` from designation matrix | **Broad sweep — pull every employee** at the company (free), filter afterward |
| Who decides relevance | Deterministic fuzzy title matcher (`titleMatcher.js`) | **LLM judge** reading raw search output, driven by an **editable system prompt** — no decision logic in code |
| Storage | JSON files (`contact-store.json`, in-memory job store) | **MongoDB** (runs, companies, employees, verdicts, settings, prompt versions, credit ledger) |
| Config | `.env` flags, redeploy to change | **Live settings UI** persisted in Mongo; `.env` only for secrets |
| Frontend | Upload → progress → download | Upload → live progress → **interactive review table** (auto + manual modes) → gated reveal → download |
| Reveal gate | Auto within `MAX_CREDITS_PER_RUN` | Credit estimate + confirm dialog; auto-mode threshold on LLM confidence |

**What carries over (proven, keep):** the resolution cascade (Apollo domain → Apollo name → Lusha domain/name → NOT_FOUND with Needs-Review sheet), bulk org pre-warm, retry/rate-limit utils, domain cleaner, Excel writer column mapping, the contact idempotency store (moves from JSON to Mongo), Apollo-first/Lusha-fallback ordering.

---

## 2. Architecture

```
 Excel upload                       ┌──────────────────────────────┐
      │                             │  React/Vite frontend          │
      ▼                             │  • run dashboard (SSE live)   │
┌──────────────┐   REST + SSE       │  • employee review table      │
│ Express API  │◄──────────────────►│  • settings & prompt editor   │
└──────┬───────┘                    │  • reveal confirm dialog      │
       │                            └──────────────────────────────┘
       ▼
┌──────────────────────────────────────────────────────────┐
│ Pipeline worker (per-company jobs, concurrency-capped)    │
│                                                           │
│ 1. RESOLVE   Apollo org enrich (bulk×10 pre-warm)         │
│ 2. SWEEP     Apollo people search — NO title filter,      │
│              paginate all employees (free)                │
│ 3. JUDGE     LLM (Claude) judges each batch against the   │
│              system prompt + designation matrix context   │
│ 4. GATE      auto-approve ≥ confidence threshold, queue   │
│              rest for manual review; credit estimate      │
│ 5. REVEAL    Apollo bulk_match ×10 (email) → Lusha        │
│              fallback for misses                          │
│ 6. EXPORT    Excel writer (34-col + metadata + review)    │
└──────────────┬───────────────────────────────────────────┘
               ▼
           MongoDB
  runs · companies · employees · settings · prompts ·
  contact_store (idempotency) · credit_ledger
```

The LLM sits in exactly one place (step 3). Everything else is deterministic plumbing.

---

## 3. Tech stack

- **Backend:** Node.js + Express (reuse v0.2 code and team familiarity), Mongoose for MongoDB
- **DB:** MongoDB (local docker for dev; Atlas or EC2 container in prod — Atlas credentials already exist at `D:\tritorc\atlas-credentials.env`)
- **LLM:** Claude API — `claude-sonnet-5` for judging (structured output via tool-forcing), model name configurable in settings
- **Frontend:** React + Vite + Tailwind (same as v0.2 client), SSE for live progress (no websocket infra needed)
- **Excel:** `exceljs` (already used in v0.2)

---

## 4. Pipeline stages (with efficiency levers)

### Stage 0 — Ingest
- Parse uploaded Excel/CSV → `{company_name, website}` rows; derive domain (reuse `domainCleaner.js`); de-dupe by domain; create `run` + `company` docs in Mongo (status: `queued`).
- **Efficiency:** reject/flag rows already fully processed in `contact_store` within a configurable freshness window (default 90 days) — "skip already-enriched companies" toggle.

### Stage 1 — Resolve
- Reuse v0.2 resolution cascade verbatim, including `APOLLO_BULK_ORG_ENRICH` pre-warm (10 domains/call).
- Store full org payload on the `company` doc (industry, headcount, revenue, description, keywords) — this becomes LLM context.

### Stage 2 — Broad people sweep (FREE)
- `POST /mixed_people/api_search` with **only** `q_organization_domains_list` — no title/seniority filter. Paginate at 100/page.
- **Hard cap per company** (setting, default 600 previews; enterprise override in UI). Beyond the cap, fall back to seniority-banded passes (`c_suite,vp,head,director,manager` first) so the most relevant people are captured before the cap hits.
- Store every preview as an `employee` doc: apollo id, first name, obfuscated last name, title, `has_email`, org info, `last_refreshed_at`.
- **Efficiency:** `has_email == false` people are stored but flagged `no_email_available` — the LLM still sees them (Lusha may have the email) but they're sorted last for Apollo reveal.

### Stage 3 — LLM judge (the core of v3)
- **No decision logic in code.** `judge.js` is a thin runner: load active system prompt from Mongo → build payload → call Claude → validate structured output → write verdicts.
- **System prompt** (seeded from a repo file `judging/system_prompt.md`, then DB-versioned and editable in the UI) contains: Tritorc's business context, the full designation matrix (auto-injected from the Excel via a build step, like `build_reference_data.py` did), customer-type guidance, and instructions to return per-person: `verdict` (enrich / skip / unsure), `confidence` (0–1), `matched_designation`, `function_group`, `reasoning` (one line).
- **Payload per call:** company context (name, industry, headcount, description, resolved customer type hint) + a batch of up to **150 employees** (id, title, seniority, location, has_email). One company = 1–4 LLM calls, never per-person calls.
- **Efficiency levers:**
  - Batch = 150 people/call (~large output budget respected); parallelize batches across companies, not within.
  - Cheap **pre-trim in code is allowed only as cost control, not judgment**: a configurable "never-send" list (e.g. `intern`, `student`, `retired`) that is OFF by default — the user opts in via settings.
  - Cache verdicts: `(title_normalized, customer_type, prompt_version)` → verdict. A repeated title at the same customer type under the same prompt version skips the LLM entirely. This is the single biggest token saver across large runs (title distributions are heavily repeated).
  - Structured output enforced via a forced tool call with a JSON schema — malformed responses auto-retry once.
- **Auditability:** every verdict stores `prompt_version`, model name, raw reasoning. Run detail view can answer "why was this person skipped."

### Stage 4 — Gate (auto + manual meet here)
- Settings define: `auto_approve_confidence` (default 0.8), `auto_mode` (on/off), per-company reveal cap, run credit budget.
- **Auto mode ON:** verdicts ≥ threshold are marked `approved`; `unsure` and below-threshold go to the review queue; if the estimated credits for approved contacts ≤ budget, reveal proceeds automatically; else the run pauses with an estimate (same estimate-then-confirm as v0.2/DATA).
- **Auto mode OFF:** everything lands in the review table pre-checked per verdict; nothing is spent until the user clicks **Reveal selected** and confirms the credit estimate.
- Manual overrides always win and are recorded (`overridden_by`, `overridden_at`) — these become future prompt-tuning signals.

### Stage 5 — Reveal (PAID, email-first)
- Apollo `bulk_match` in batches of 10, `id`-based (from search), email only by default (phone reveal = setting, off by default, webhook endpoint already scaffolded in v0.2).
- Check Mongo `contact_store` before every reveal (idempotency — never pay twice, across all runs).
- **Lusha fallback** per contact when Apollo returns no verified email: `search-and-enrich` with name+domain, `reveal:["emails"]`. Respect Lusha 402/429/451 handling from the reference doc.
- Every credit spent writes a `credit_ledger` entry (run, company, person, engine, action, credits) → the dashboard shows live spend.

### Stage 6 — Export
- Excel: **Contacts** sheet (34-col format from v0.2, plus `_Verdict`, `_Confidence`, `_Reasoning`, `_Prompt Version`, `_Source`), **Run Log** sheet, **Needs Review** sheet (unresolved companies + skipped-but-unsure people).
- Files stored under `outputs/` keyed by run id (as today) + row in Mongo for history listing.

---

## 5. MongoDB collections

| Collection | Key fields | Notes |
|---|---|---|
| `runs` | status, counts, credit totals, settings snapshot, prompt_version used | settings are **snapshotted per run** for reproducibility |
| `companies` | run_id, input row, resolved org payload, resolution source, customer_type, status | one doc per company per run |
| `employees` | company_id, run_id, apollo preview fields, verdict {verdict, confidence, reasoning, prompt_version}, review {approved, overridden_by}, reveal {status, email, engine, credits} | the central working table; indexed on (run_id, verdict.verdict), (company_id) |
| `contact_store` | domain, person key (apollo id / linkedin / name+domain), revealed email, engine, revealed_at | global idempotency, replaces `contact-store.json`; unique index on person key |
| `verdict_cache` | title_norm, customer_type, prompt_version → verdict | TTL optional; biggest LLM cost saver |
| `settings` | singleton doc: all knobs (caps, thresholds, auto_mode, engine toggles, model name, never-send list) | edited via UI; `.env` holds secrets only |
| `prompts` | version, body, created_by, created_at, active flag | system prompt versioning; seeded from repo file |
| `credit_ledger` | run_id, company_id, employee_id, engine, action, credits, at | powers spend dashboard + monthly reporting |

---

## 6. API surface (Express)

```
POST   /api/runs                 upload file, create run (multipart)
GET    /api/runs                 history list
GET    /api/runs/:id             run detail + counts
GET    /api/runs/:id/events      SSE: live progress (company statuses, spend)
GET    /api/runs/:id/companies   paged company list
GET    /api/companies/:id/employees   review table data (filter by verdict)
PATCH  /api/employees/:id        manual override (approve/skip)
POST   /api/runs/:id/estimate    credit estimate for current approved set
POST   /api/runs/:id/reveal      confirm + start reveal stage
GET    /api/runs/:id/export      download Excel
GET/PUT /api/settings            live settings
GET/POST /api/prompts            list versions / save new version
POST   /api/prompts/:v/activate  switch active prompt
POST   /api/webhook/apollo       phone-reveal webhook (existing scaffold)
```

Auth: simple shared-secret login for the team initially (JWT cookie); per-user accounts deferred unless attribution is needed sooner.

---

## 7. Frontend screens

1. **Upload / New Run** — drag-drop Excel, column mapping preview (auto-detect name/website columns), run options (auto mode on/off, budget for this run).
2. **Run Dashboard** — live SSE table: per-company status chips (resolving → sweeping → judging → awaiting review → revealing → done), running totals (companies, employees found, judged, approved, credits spent/estimated), pause/resume.
3. **Review Table** (the heart of manual mode) — employees grouped by company; columns: name, title, verdict badge, confidence bar, reasoning tooltip, has_email, checkbox. Bulk actions (approve all ≥ X, skip all below Y). Filter: unsure only / overridden / all.
4. **Reveal Confirm Dialog** — itemized estimate (Apollo n × 1cr, Lusha fallback est.), budget remaining, confirm button.
5. **Settings** — every knob from §4 live-editable; separate **Prompt Editor** tab: textarea with the active system prompt, version history, "save as new version", diff view between versions.
6. **History / Exports** — past runs, download links, per-run spend.

---

## 8. Settings (all live-editable, Mongo-backed)

```yaml
auto_mode: true
auto_approve_confidence: 0.8
sweep_cap_per_company: 600
reveal_cap_per_company: 8
run_credit_budget: 250
engine_order: [apollo, lusha]
lusha_fallback: true
reveal_phone: false
llm_model: claude-sonnet-5
judge_batch_size: 150
verdict_cache: true
never_send_titles: []          # off by default — LLM sees everyone
contact_freshness_days: 90     # skip re-enriching within this window
```

---

## 9. Build phases

| Phase | Deliverable | Est. scope |
|---|---|---|
| **P0** | Repo scaffold (`enrich_v3/`), Mongo docker-compose, Mongoose models, settings seed, designation-matrix build step (Excel → JSON injected into prompt) | foundation |
| **P1** | Port from v0.2: resolution cascade, apollo/lusha clients, retry/rate-limit, domain cleaner, Excel writer → adapted to Mongo persistence | reuse-heavy |
| **P2** | Broad sweep stage: unfiltered paginated people search, per-company cap + seniority-banded fallback, employee docs | new |
| **P3** | LLM judge: `system_prompt.md` v1 (business context + matrix), thin runner with structured output, verdict cache, batch orchestration | **the core** |
| **P4** | Gate + reveal: auto/manual flow, estimate endpoint, reveal worker with idempotency + Lusha fallback + credit ledger | new + port |
| **P5** | Frontend: upload, dashboard (SSE), review table, reveal dialog | new |
| **P6** | Settings UI + prompt editor with versioning | new |
| **P7** | Export, history, auth, docker packaging for EC2 (mirror lead-discovery deployment pattern) | wrap-up |

Test checkpoints: P1 — resolve 10 sample companies with real keys, zero contact credits. P3 — judge a captured sweep fixture offline, eyeball verdicts vs. the old titleMatcher's output on the same data (regression sanity). P4 — end-to-end on 10 companies within a 25-credit budget.

---

## 10. Efficiency summary (why this is cheap to run)

1. People **search is free** — the broad sweep costs zero credits regardless of volume; only pagination time.
2. **Verdict cache** collapses repeated titles per (customer_type, prompt_version) — after a few companies, most judgments are cache hits.
3. **Batched LLM calls** (150 people/call) + Haiku-downgrade option in settings if Sonnet proves unnecessary.
4. **Bulk endpoints everywhere** — org enrich ×10, people match ×10, Lusha enrich ×100.
5. **Global idempotency store** — a contact revealed in any past run is never paid for again.
6. **has_email pre-sort** — Apollo reveals target people Apollo actually has; everyone else routes straight to Lusha consideration.
7. **Budget gates** at estimate-time and a live ledger, so overspend is impossible without an explicit confirm.

---

## 11. Risks / open items

- **Sweep volume on enterprise accounts** — 10k+ employees would mean 100+ free search pages and heavy LLM batches; mitigated by cap + seniority-banded fallback, but the cap default (600) needs validation on a real enterprise domain in P2.
- **LLM verdict drift between prompt versions** — mitigated by prompt versioning + settings snapshot per run; consider a small "golden set" of title→expected-verdict fixtures run against any new prompt version before activation.
- **Lusha search billing** — Lusha charges for search even without reveal; keep `lusha_fallback` per-contact (not per-company sweep) and surface its spend separately in the ledger.
- **Apollo master-key requirement** for people search — confirm current plan tier before P2.
- **GDPR 451s** on European contacts — log and skip, never retry-loop.
