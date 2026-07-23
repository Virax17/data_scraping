"""Thin LLM runner. Loads the active system prompt (Mongo, seeded from
system_prompt.md), injects the targeting matrix, batches employees, calls
Claude with structured output, applies the verdict cache. NO decision logic
here — the prompt is the judge."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic
from pydantic import ValidationError

from app.config import get_config, get_live_settings
from app.core.classify import load_icp, load_targeting
from app.judging.schema import JudgeResponse
from app.models.employee import Employee, Verdict
from app.models.misc import Prompt, VerdictCacheEntry
from app.providers.cerebras_client import CerebrasClient

log = logging.getLogger(__name__)

JUDGING_DIR = Path(__file__).parent
_anthropic: anthropic.AsyncAnthropic | None = None
_cerebras: CerebrasClient | None = None


def _anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.AsyncAnthropic(api_key=get_config().anthropic_api_key)
    return _anthropic


def _cerebras_client() -> CerebrasClient:
    global _cerebras
    if _cerebras is None:
        _cerebras = CerebrasClient()
    return _cerebras


async def ensure_active_prompt() -> Prompt:
    """Seed v1 from the repo file on first boot; return the active prompt."""
    active = await Prompt.find_one(Prompt.active == True)  # noqa: E712
    if active:
        return active
    body = (JUDGING_DIR / "system_prompt.md").read_text(encoding="utf-8")
    prompt = Prompt(version=1, body=body, active=True, created_by="seed")
    await prompt.insert()
    return prompt


def _compact_matrix(targeting: dict) -> str:
    """Terse designation list — no JSON punctuation — for small-context
    providers (Cerebras free tier's 8K cap). ~3-4x fewer tokens than the
    full indented JSON dump."""
    lines = []
    for customer_type, groups in targeting.items():
        lines.append(customer_type + ":")
        for fg, titles in groups.items():
            lines.append(f"  {fg}: {', '.join(titles)}")
    return "\n".join(lines)


def _render_prompt(body: str) -> str:
    targeting = load_targeting()
    icp = load_icp()
    matrix_md = _compact_matrix(targeting)
    icp_summary = ", ".join(icp.get("industries", {}).keys())
    return (body
            .replace("{{TARGETING_MATRIX}}", matrix_md)
            .replace("{{ICP_SUMMARY}}", icp_summary))


def _title_norm(title: str | None) -> str:
    return " ".join((title or "").lower().split())


async def _cache_lookup(title: str | None, customer_type: str,
                        prompt_version: int) -> VerdictCacheEntry | None:
    if not title:
        return None
    return await VerdictCacheEntry.find_one(
        VerdictCacheEntry.title_norm == _title_norm(title),
        VerdictCacheEntry.customer_type == customer_type,
        VerdictCacheEntry.prompt_version == prompt_version,
    )


def _company_context(company) -> str:
    org = company.org or {}
    return json.dumps({
        "name": company.input_name,
        "domain": company.domain,
        "industry": org.get("industry"),
        "employees": org.get("estimated_num_employees"),
        "description": (org.get("short_description") or "")[:600],
        "keywords": (org.get("keywords") or [])[:20],
        "customer_type_hint": company.customer_type,
        "classification_confidence": (company.classification or {}).get("confidence"),
        "size_tier": company.size_tier,
    }, ensure_ascii=False)


async def judge_company(company, employees: list[Employee]) -> int:
    """Judge all unjudged employees of one company. Writes Verdict onto each
    Employee doc. Returns the number judged (cache hits included)."""
    settings = await get_live_settings()
    prompt = await ensure_active_prompt()
    provider = settings.get("llm_provider", "anthropic")
    is_cerebras = provider == "cerebras"
    system = _render_prompt(prompt.body)
    customer_type = company.customer_type or "Unknown / Ambiguous"
    # classify_company() is a deterministic hint, not a gate -- when it can't
    # resolve a customer_type, every such company shares this one literal
    # cache key. Reading/writing verdicts under it would let a cached verdict
    # for one ambiguous company's title (e.g. a civil-earthwork contractor)
    # get silently reused for a completely different ambiguous company (e.g.
    # a nuclear EPC firm) with the same title but a different real context.
    use_cache = bool(settings.get("verdict_cache", True)) and company.customer_type is not None
    if is_cerebras:
        batch_size = int(settings.get("cerebras_judge_batch_size", 15))
        model = settings.get("cerebras_model", "gpt-oss-120b")
    else:
        batch_size = int(settings.get("judge_batch_size", 150))
        model = settings.get("llm_model", "claude-opus-4-8")

    pending: list[Employee] = []
    judged = 0

    # 1) cache pass
    for emp in employees:
        if emp.verdict is not None:
            continue
        cached = await _cache_lookup(emp.title, customer_type, prompt.version) if use_cache else None
        if cached:
            emp.verdict = Verdict(
                verdict=cached.verdict, confidence=cached.confidence,
                matched_designation=cached.matched_designation,
                function_group=cached.function_group,
                reasoning=cached.reasoning, prompt_version=prompt.version,
                from_cache=True,
            )
            await emp.save()
            judged += 1
        else:
            pending.append(emp)

    # 2) LLM batches
    anthropic_client = None if is_cerebras else _anthropic_client()
    cerebras_client = _cerebras_client() if is_cerebras else None

    for i in range(0, len(pending), batch_size):
        batch = pending[i:i + batch_size]
        payload = {
            "company": json.loads(_company_context(company)),
            "employees": [
                {
                    "ref": idx,
                    "name": e.full_name or f"{e.first_name or ''} {e.last_name or ''}".strip(),
                    "title": e.title,
                    "seniority": e.seniority,
                    "location": ", ".join(x for x in [e.city, e.country] if x),
                    "has_email_in_apollo": e.has_email,
                }
                for idx, e in enumerate(batch)
            ],
        }
        payload_json = json.dumps(payload, ensure_ascii=False)

        result: JudgeResponse | None = None
        for attempt in range(2):
            error: Exception | None = None
            try:
                if is_cerebras:
                    raw = await cerebras_client.judge_completion(model, system, payload_json)
                    result = JudgeResponse(**raw) if raw is not None else None
                else:
                    response = await anthropic_client.messages.parse(
                        model=model,
                        max_tokens=16000,
                        system=[{"type": "text", "text": system,
                                 "cache_control": {"type": "ephemeral"}}],
                        messages=[{"role": "user", "content": payload_json}],
                        output_format=JudgeResponse,
                    )
                    result = response.parsed_output
            except (ValidationError, anthropic.APIError) as exc:
                result = None
                error = exc

            if result is not None:
                break
            is_last = attempt == 1
            log.log(
                logging.ERROR if is_last else logging.WARNING,
                "judge (%s) call for company %s failed (attempt %d/%d)%s%s",
                provider, company.id, attempt + 1, 2,
                ", retrying" if not is_last else ", giving up",
                f": {error}" if error else " (unparseable output)",
            )

        if result is None:
            continue

        returned_refs = {v.employee_ref for v in result.verdicts}
        expected_refs = set(range(len(batch)))
        if returned_refs != expected_refs:
            log.warning(
                "judge (%s) ref mismatch for company %s: expected %s, got %s",
                provider, company.id, expected_refs, returned_refs)

        for v in result.verdicts:
            if not 0 <= v.employee_ref < len(batch):
                continue
            emp = batch[v.employee_ref]
            emp.verdict = Verdict(
                verdict=v.verdict, confidence=v.confidence,
                matched_designation=v.matched_designation,
                function_group=v.function_group,
                reasoning=v.reasoning, prompt_version=prompt.version,
            )
            await emp.save()
            judged += 1
            if use_cache and emp.title:
                exists = await _cache_lookup(emp.title, customer_type, prompt.version)
                if not exists:
                    await VerdictCacheEntry(
                        title_norm=_title_norm(emp.title),
                        customer_type=customer_type,
                        prompt_version=prompt.version,
                        verdict=v.verdict, confidence=v.confidence,
                        matched_designation=v.matched_designation,
                        function_group=v.function_group,
                        reasoning=v.reasoning,
                    ).insert()

    return judged
