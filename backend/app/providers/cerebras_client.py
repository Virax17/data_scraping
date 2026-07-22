"""Cerebras Inference client (OpenAI-compatible chat completions) used as an
alternate judge engine. Free-tier aware: paced to 5 requests/minute and small
contexts (8K cap) — pair with a small judge_batch_size.

Structured output via response_format json_schema (strict)."""

from __future__ import annotations

import json

from app.config import get_config
from app.providers.base import BaseClient

# Hand-written schema (no numeric bounds — strict mode rejects them);
# validation against the real pydantic model happens in judge.py.
JUDGE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "employee_ref": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["enrich", "skip", "unsure"]},
                    "confidence": {"type": "number"},
                    "matched_designation": {"type": ["string", "null"]},
                    "function_group": {"type": ["string", "null"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["employee_ref", "verdict", "confidence",
                             "matched_designation", "function_group", "reasoning"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


class CerebrasClient(BaseClient):
    base_url = "https://api.cerebras.ai/v1"

    def __init__(self):
        # Free tier: 5 req/min -> 1 request per 12s. Retries on 429 are
        # handled by BaseClient's backoff.
        super().__init__(requests_per_second=1 / 12)
        api_key = get_config().cerebras_api_key
        if not api_key:
            raise RuntimeError("CEREBRAS_API_KEY is not set in .env")
        self._client.headers["Authorization"] = f"Bearer {api_key}"
        self._client.headers["Content-Type"] = "application/json"

    async def judge_completion(self, model: str, system: str, user_payload: str) -> dict | None:
        """One judge call. Returns the parsed JSON dict or None on failure."""
        resp = await self.request("POST", "/chat/completions", json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_payload},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "judge_response", "strict": True,
                                "schema": JUDGE_JSON_SCHEMA},
            },
            "max_completion_tokens": 4000,
            "temperature": 0,
        })
        if resp.status_code != 200:
            return None
        try:
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError, ValueError):
            return None
