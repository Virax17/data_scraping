"""Lusha V3 REST client — fallback engine. Search AND enrich both cost credits
on Lusha, so it only runs per-contact when Apollo yields no verified email.

Request/response shape verified directly against the live API (2026-07):
both search-and-enrich endpoints take a `companies`/`contacts` ARRAY of
identifier objects (a flat {"domain": ...} body is rejected outright with a
schema error), and the response wraps matches in a top-level `results` array
— NOT `companies`/`contacts`/`data`. A miss comes back as HTTP 200 with
`{"error": {...}}` in place of the result object, not a non-200 status."""

from __future__ import annotations

from app.config import get_config
from app.providers.base import BaseClient


def _first_result(data: dict) -> dict | None:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict) or "error" in first:
        return None
    return first


class LushaClient(BaseClient):
    base_url = "https://api.lusha.com/v3"

    def __init__(self):
        super().__init__()
        self._client.headers["api_key"] = get_config().lusha_api_key
        self._client.headers["Content-Type"] = "application/json"

    async def company_search_enrich(self, domain: str | None = None,
                                    name: str | None = None) -> dict | None:
        identifier: dict = {}
        if domain:
            identifier["domain"] = domain
        elif name:
            identifier["name"] = name
        else:
            return None
        resp = await self.request("POST", "/companies/search-and-enrich",
                                  json={"companies": [identifier]})
        if resp.status_code != 200:
            return None
        return _first_result(resp.json())

    async def contact_search_enrich(self, first_name: str, last_name: str,
                                    company_domain: str) -> dict | None:
        """search-and-enrich, email only. 402=no credits, 451=GDPR block."""
        resp = await self.request("POST", "/contacts/search-and-enrich", json={
            "contacts": [{
                "firstName": first_name,
                "lastName": last_name,
                "companyDomain": company_domain,
            }],
            "reveal": ["emails"],
        })
        if resp.status_code in (402, 451) or resp.status_code != 200:
            return None
        return _first_result(resp.json())
