"""Apollo REST client. Reference: Apollo_Lusha_API_Reference_Tritorc.md.
People search is FREE (no credits); org enrich and people match cost credits."""

from __future__ import annotations

from app.config import get_config
from app.providers.base import BaseClient


class ApolloClient(BaseClient):
    base_url = "https://api.apollo.io/api/v1"

    def __init__(self):
        super().__init__()
        self._client.headers["x-api-key"] = get_config().apollo_api_key
        self._client.headers["Content-Type"] = "application/json"

    async def organization_enrich(self, domain: str | None = None,
                                  name: str | None = None) -> dict | None:
        """GET /organizations/enrich — costs credits when data is returned."""
        params = {}
        if domain:
            params["domain"] = domain
        if name:
            params["name"] = name
        resp = await self.request("GET", "/organizations/enrich", params=params)
        if resp.status_code != 200:
            return None
        return resp.json().get("organization")

    async def organization_search(self, name: str) -> dict | None:
        """POST /mixed_companies/search by name — FREE. Returns best match."""
        resp = await self.request("POST", "/mixed_companies/search",
                                  json={"q_organization_name": name, "per_page": 5})
        if resp.status_code != 200:
            return None
        orgs = resp.json().get("organizations") or resp.json().get("accounts") or []
        return orgs[0] if orgs else None

    async def people_search_page(self, domain: str, page: int = 1, per_page: int = 100,
                                 seniorities: list[str] | None = None) -> dict:
        """POST /mixed_people/api_search — FREE, previews only (no email/phone).
        No title filter: the broad sweep pulls everyone; the LLM judge filters."""
        body: dict = {
            "q_organization_domains_list": [domain],
            "page": page,
            "per_page": per_page,
        }
        if seniorities:
            body["person_seniorities"] = seniorities
        resp = await self.request("POST", "/mixed_people/api_search", json=body)
        if resp.status_code != 200:
            return {"people": [], "pagination": {}}
        data = resp.json()
        return {
            "people": data.get("people", []),
            "pagination": data.get("pagination", {}),
        }

    async def people_bulk_match(self, apollo_ids: list[str]) -> dict:
        """POST /people/bulk_match — COSTS CREDITS. Up to 10 ids per call.
        Email only: never sets reveal_phone_number."""
        details = [{"id": pid} for pid in apollo_ids[:10]]
        resp = await self.request("POST", "/people/bulk_match",
                                  json={"details": details,
                                        "reveal_personal_emails": False})
        if resp.status_code != 200:
            return {"matches": [], "credits_consumed": 0}
        data = resp.json()
        return {
            "matches": data.get("matches", []),
            "credits_consumed": data.get("credits_consumed", len(details)),
        }
