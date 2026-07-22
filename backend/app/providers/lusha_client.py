"""Lusha V3 REST client — fallback engine. Search AND enrich both cost credits
on Lusha, so it only runs per-contact when Apollo yields no verified email."""

from __future__ import annotations

from app.config import get_config
from app.providers.base import BaseClient


class LushaClient(BaseClient):
    base_url = "https://api.lusha.com/v3"

    def __init__(self):
        super().__init__()
        self._client.headers["api_key"] = get_config().lusha_api_key
        self._client.headers["Content-Type"] = "application/json"

    async def company_search_enrich(self, domain: str | None = None,
                                    name: str | None = None) -> dict | None:
        body = {}
        if domain:
            body["domain"] = domain
        elif name:
            body["name"] = name
        resp = await self.request("POST", "/companies/search-and-enrich", json=body)
        if resp.status_code != 200:
            return None
        data = resp.json()
        companies = data.get("companies") or data.get("data") or []
        return companies[0] if isinstance(companies, list) and companies else data or None

    async def contact_search_enrich(self, first_name: str, last_name: str,
                                    company_domain: str) -> dict | None:
        """search-and-enrich, email only. 402=no credits, 451=GDPR block."""
        resp = await self.request("POST", "/contacts/search-and-enrich", json={
            "firstName": first_name,
            "lastName": last_name,
            "companyDomain": company_domain,
            "reveal": ["emails"],
        })
        if resp.status_code in (402, 451) or resp.status_code != 200:
            return None
        data = resp.json()
        contacts = data.get("contacts") or data.get("data") or []
        return contacts[0] if isinstance(contacts, list) and contacts else data or None
