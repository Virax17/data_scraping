# Tritorc Enrichment v3 — session plan & status

## Status overview

### ✅ Complete (implemented, tested, committed this session)
- **Region/city targeting**: country/city dropdowns on upload, per-company
  location override, Apollo `person_locations`/`organization_locations`
  filters + lenient client-side backstop (`search_filters.py`).
- **Search customization**: seniority, titles, keywords, headcount ranges
  (`SearchFiltersForm.tsx`, `settings.yaml` search_defaults).
- **Pagination bug fix** (root cause of "very low employee count"): Apollo
  free preview has no `pagination.total_pages` field — fixed to page on
  `total_entries` (`apollo_client.py`, `pipeline.py`).
- **Dedup bug fix** ("only one name per company"): added `apollo_id` dedup
  tier since free-preview people never carry `full_name` (`dedup.py`).
- **Lusha API fully broken → fixed**: real API needs
  `{"companies":[...]}`/`{"contacts":[...]}` wrapped bodies and reads
  `results` (`lusha_client.py`), verified against live API + OpenAPI spec.
- **Lusha domain-fallback path** in `resolve_company` when Apollo org match
  lacks a domain.
- **BaseClient retry-delay cap**: `MAX_RETRY_DELAY = 30.0`, guards against a
  bogus `Retry-After` (Cerebras once sent `86400`, caused a 24h sleep).
- **Cerebras multi-key rotation**: 3 keys added, round-robin
  `_SingleKeyClient` wrapper for higher free-tier throughput.
- **Null-domain guard**: Apollo sweep now refuses to run with no domain
  (previously returned unscoped garbage silently).
- **Stop / Delete run lifecycle**: cooperative-cancellation checkpoints in
  `process_company`/`reveal_company`, `POST /runs/{id}/stop`,
  `DELETE /runs/{id}` (full cleanup: companies, employees, export files, run
  doc; `contact_store` intentionally left untouched). Frontend buttons wired
  in `runs/[runId]/page.tsx` and `runs/page.tsx`.
- **Tests**: 81/81 passing across all of the above
  (`test_search_filters.py`, `test_apollo_client.py`, `test_uploads.py`,
  `test_lusha_client.py`, `test_base_client.py`, `test_config.py`,
  `test_cerebras_client.py`, `test_run_lifecycle.py`, plus extensions to
  `test_pipeline_e2e.py`, `test_exports.py`, `test_classify.py`,
  `test_runs_api.py`).

### ⏳ Incomplete (designed, NOT yet implemented — pending plan approval)
- **PR 0** — Add "Project Manager" / "Capital Projects Manager" to End
  User's targeting matrix (currently missing; present for 3 other customer
  types). Cross-checked against a real export (`usa project .xlsx`) which
  confirms the title is common in the wild but didn't contain a labeled
  End-User row, so the gap itself is still inferred, not directly observed.
- **PR 1** — Prompt & render simplification (shrink `system_prompt.md`
  ~35%, always use compact matrix for both providers, drop `target_region`
  from judge context).
- **PR 2** — Bound `reasoning` output length + add retry-on-failure in the
  judge batch loop.
- **PR 3** — Raise `cerebras_judge_batch_size` 15 → 40-50 (after PR 1+2 are
  measured live).
- **PR 4** — Replace `employee_ref` (Mongo ObjectId) with a positional
  index + a ref-set validation guard.
- **Audit more real exports** for other targeting-matrix gaps and to build a
  golden-set regression fixture (needs files that have actually been through
  this app's judge — `usa project .xlsx` is a raw pre-judge export, useful
  for title/keyword vocabulary only).

---

## Context

The judge (`backend/app/judging/judge.py`) is the one place an LLM decides who
gets enriched. It's already got the two big cost levers in place (broad free
sweep + a verdict cache keyed on title/customer_type), but a full-file audit
found real remaining waste and two latent accuracy risks:

- The system prompt (127 lines) duplicates the targeting matrix in prose,
  and instructs the LLM to size-calibrate volume — work `reveal_cap_by_size_tier`
  already does deterministically downstream. That's tokens spent asking the
  LLM to do something the code overrides anyway, and it makes verdict
  confidence potentially size-dependent in a way that's inconsistent with a
  cache keyed only on `(title, customer_type)`.
- Only the Cerebras path uses the compact (lossless, test-proven) matrix
  format; Anthropic still pays for the verbose JSON dump. Cerebras — the
  *default* provider — has zero prompt caching available at all, so its
  system-prompt tokens are repaid in full on every single call.
- `target_region` is threaded into the judge's company context, but
  `matches_region()` already hard-filters at the sweep stage — by the time an
  employee reaches the judge, region has already decided who's in scope.
  It's dead weight in the payload.
- No retry on a failed/malformed judge response — a transient API hiccup or
  one bad parse permanently orphans that batch's employees for the run, with
  no error surfaced beyond a log line.
- `employee_ref` echoes a full ~24-char Mongo ObjectId per verdict, in both
  directions (input `ref` + output `employee_ref`) — pure token overhead with
  a cheap positional-index replacement, though it introduces a new silent
  failure mode (off-by-one misattribution) that needs a matching guard.

Goal: cut per-call token cost (mainly on the uncached Cerebras path, which is
the current default and the one paying full price every time), while
tightening the judge's actual accuracy (bounding runaway reasoning output,
adding retry so batches don't silently vanish, removing prompt sections that
fight the deterministic gate instead of complementing it).

## Recommended approach (ranked; ship in this order)

**PR 0 — Fix a real targeting gap: "Project Manager" missing for End Users**
(do this first, independent of the token-efficiency work below — it's an
accuracy/coverage bug, not an optimization):
- `backend/app/reference_data/targeting.json` already lists "Project Manager"
  under 3 customer types (EPC / Project Engineering Organizations, Service
  Providers / Turnaround & Bolting Specialists, Mechanical / Maintenance
  Contractors) — but **not** under "End User (Plant / Facility Owner)", the
  most common customer type. Plant-side capital projects and turnarounds are
  routinely run by a "Project Manager" or "Capital Projects Manager," so
  End-User companies are very likely having these titles skipped or marked
  `unsure` today, since the judge prompt matches titles against the
  customer-type-specific section of the matrix.
  - Cross-checked against a real enriched export (`usa project .xlsx`,
    1000 rows, Apollo-style schema matching the app's own Name/Title/Company/
    Email/Industry/Keywords/LinkedIn/Website/City/State/Country/Address
    columns): "Project Manager" and close variants ("Project Manager -
    Energy Solutions") appear routinely at EPC/construction/services firms
    (Burns & McDonnell, Fluor, MasTec, Michels) — customer types that already
    have "Project Manager" in the matrix, so this sample confirms the title
    is common in the wild but doesn't itself contain an End-User example.
    The gap is still inferred from matrix inspection, not yet directly
    observed in a labeled End-User row — worth confirming against a file
    that has judged End-User companies before/after the fix.
  - Add "Project Manager" and "Capital Projects Manager" to End User's
    "Operations & Turnarounds" group (natural fit alongside Turnaround
    Manager/Shutdown Manager — these are the people who run the exact
    projects Tritorc's bolting tools get used on).
  - After adding, re-run `python build_reference_data.py`
    (`backend/app/reference_data/`) per the README to regenerate whatever
    derived reference data depends on `targeting.json` (check the script for
    what it actually builds before assuming a rebuild is needed).
- **Audit real output files for other gaps**: cross-reference more real
  judged exports (title + customer_type + verdict/reasoning columns) against
  `targeting.json` to find: (a) other real-world titles that should clearly
  be `enrich` but aren't in any customer type's matrix, (b) titles that ARE
  in the matrix but got `skip`/`unsure` anyway (a prompt or classify.py
  customer_type-detection bug, not a matrix gap), (c) a candidate "golden
  set" — a fixture file of `(title, customer_type) -> expected verdict`
  pairs — to add as a regression test so future prompt edits (like PR 1
  below) can be checked against known-good judgments before shipping, not
  just spot-checked ad hoc. Note: `usa project .xlsx` is a raw Apollo-style
  export (no verdict/reasoning columns of its own), so it's useful for
  title/keyword/industry vocabulary but not directly for a golden-set verdict
  fixture — that needs a file that's actually been through this app's judge.

**PR 1 — Prompt & render simplification** (one `prompt_version` bump, one
cache cold-start — expected and fine, do this in a low-traffic window):
- Rewrite `backend/app/judging/system_prompt.md`:
  - Cut the ~24-line "What Tritorc sells to whom" prose block down to a
    2–3 line pointer at the matrix (keep only the "fuzzy match, not a rigid
    whitelist" instruction — the matrix already enumerates the who/what).
  - Shrink "Priority #2: calibrate volume to company size" from 31 lines to
    ~7: keep *only* the one thing the deterministic cap can't do (spot
    plant-level authority vs. disconnected global-corporate roles at large
    companies), explicitly tell the LLM the reveal cap already scales
    contacts-per-company by size so it shouldn't try to compensate.
  - Tighten Priority #1's lead-in prose (4 lines → 2), keep all four
    authority-signal bullets as-is — that's the real judgment logic.
  - Target: ~127 lines/7176 bytes → ~80 lines/~4650 bytes (~35% smaller),
    resent on every uncached Cerebras call, so this is a per-call saving, not
    one-time.
- In `backend/app/judging/judge.py::_render_prompt`, drop the `compact`
  parameter/branch — always use `_compact_matrix()` for both providers
  (proven lossless by the existing `test_compact_matrix_is_smaller_than_json_and_lossless`
  test; no nesting in `targeting.json` beyond 2 levels that compact can't
  represent). One render path instead of two.
- Remove `target_region` from `_company_context()` (judge.py ~line 104) —
  redundant with sweep-stage region filtering, zero remaining decision value.

**PR 2 — Output bounding + retry** (no prompt_version bump needed):
- Tighten the reasoning-length instruction in the prompt from "one short
  sentence" to an explicit bound (e.g. "≤12 words, name only the authority
  signal"), **and** add a defensive truncation (~150 chars) in code — either
  a Pydantic validator on `EmployeeVerdict.reasoning` (`schema.py`) or a
  post-parse truncation in `judge.py`. Bounds worst-case output tokens and
  keeps `VerdictCacheEntry.reasoning` from bloating the cache collection.
- Add one bounded retry in `judge_company`'s per-batch loop (`judge.py`
  ~lines 170–193) when `judge_completion` returns `None` or raises
  `ValidationError` — log a warning and retry once with the same payload;
  only log `error`/skip on a second failure. While here, confirm whether
  Anthropic's `messages.parse()` can raise uncaught on a schema mismatch
  (currently no try/except around it) — if so, wrap it the same way so a bad
  parse degrades to "skip this batch" instead of crashing the whole company.

**PR 3 — Batch-size tuning** (after PR 1+2 land and are measured live):
- Raise `cerebras_judge_batch_size` (settings.yaml) from 15 toward 40–50 as a
  first step. Budget check: trimmed system prompt (~1700 tokens) + N×(~35-40
  input tokens/employee) fits comfortably under 8K context; the real ceiling
  is Cerebras's fixed `max_completion_tokens: 4000` (cerebras_client.py),
  which at ~30-35 output tokens/verdict supports ~110-130 verdicts before
  truncation — so batch_size 40-50 has real headroom, but don't push all the
  way to Anthropic's 150 without re-measuring against real responses.
  Sequenced after PR 2 because a bigger batch means a failed/malformed
  response now loses more employees at once — the retry + reasoning-bound
  from PR 2 directly reduce that blast radius.

**PR 4 — `employee_ref` → positional index** (do last, own validation guard):
- Switch `EmployeeVerdict.employee_ref` from the echoed Mongo ObjectId string
  to a positional integer matching the batch's array index. Saves ~10-12
  tokens/verdict (both directions), meaningful at scale (~1500-1800 output
  tokens on a full 150-employee Anthropic batch). Confirmed via repo-wide
  grep that `employee_ref` is used nowhere except the in-memory match in
  `judge.py:196` — safe to change in isolation.
  - **Required alongside**: after parsing `result.verdicts`, assert the
    returned ref set is exactly `{0, ..., len(batch)-1}` with no duplicates
    or gaps; log/flag a warning if not. ObjectId typos silently drop one
    verdict (`emp is None` → `continue`); a positional off-by-one can
    silently *misattribute* a wrong employee's verdict onto another (both
    refs resolve to valid, non-None employees) — this guard is what makes
    that failure loud instead of silent-and-wrong.

## Critical files

- `backend/app/reference_data/targeting.json` — add missing End User titles (PR 0)
- `backend/app/judging/system_prompt.md` — the rewrite (PR 1)
- `backend/app/judging/judge.py` — render path, `_company_context`, retry loop, ref matching (PR 1, 2, 4)
- `backend/app/judging/schema.py` — reasoning bound / ref type (PR 2, 4)
- `backend/app/providers/cerebras_client.py` — batch-size-relevant output cap, no changes needed unless PR 3 shows the 4000-token cap needs raising too
- `backend/app/settings.yaml` — `cerebras_judge_batch_size` (PR 3)
- `backend/tests/test_judging.py` — existing compact-matrix test to extend/reuse; add coverage for retry, ref-validation guard, reasoning truncation

## Verification

- `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -v` after each PR — extend `test_judging.py` with: retry-on-None/ValidationError (mock `judge_completion` to fail once then succeed), ref-set validation guard (feed a batch response with a duplicate/missing index and assert the warning fires), reasoning truncation (feed an oversized reasoning string).
- Manual: re-run a real judge pass (upload a small test file, or re-sweep an existing company) and confirm verdicts are materially the same shape/quality as before the prompt rewrite — spot-check a handful of known titles against pre-rewrite verdicts to catch any drift from the Priority #2 shrink.
- After PR 1: expect and confirm a `prompt_version` bump in Mongo (`ensure_active_prompt`/`Prompt.body` diff) and that the verdict cache cold-starts cleanly (new verdicts get created under the new version, old ones aren't reused incorrectly).
- After PR 3: watch a real Cerebras run's logs for `429`s or truncated/malformed JSON at the new batch size before pushing it higher.
