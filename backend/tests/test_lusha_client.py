"""Lusha v3 search-and-enrich: request must wrap identifiers in a
companies/contacts array, response must be read from `results` (not
companies/contacts/data) — verified against the live API on 2026-07.
A flat {"domain": ...} body is rejected outright with a schema error."""

from app.providers.lusha_client import LushaClient


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


async def _capture(monkeypatch, response):
    captured = {}

    async def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return response

    monkeypatch.setattr(LushaClient, "request", fake_request)
    return captured


async def test_company_search_by_domain_wraps_in_array(monkeypatch):
    captured = await _capture(monkeypatch, _Response(200, {"results": [{"domain": "www.acme.com"}]}))
    client = LushaClient()
    org = await client.company_search_enrich(domain="acme.com")
    assert captured["json"] == {"companies": [{"domain": "acme.com"}]}
    assert org == {"domain": "www.acme.com"}


async def test_company_search_by_name_wraps_in_array(monkeypatch):
    captured = await _capture(monkeypatch, _Response(200, {"results": [{"domain": "www.acme.com"}]}))
    client = LushaClient()
    await client.company_search_enrich(name="Acme")
    assert captured["json"] == {"companies": [{"name": "Acme"}]}


async def test_company_search_domain_takes_priority_over_name(monkeypatch):
    captured = await _capture(monkeypatch, _Response(200, {"results": []}))
    client = LushaClient()
    await client.company_search_enrich(domain="acme.com", name="Acme")
    assert captured["json"] == {"companies": [{"domain": "acme.com"}]}


async def test_company_search_empty_results_returns_none(monkeypatch):
    await _capture(monkeypatch, _Response(200, {"results": []}))
    client = LushaClient()
    assert await client.company_search_enrich(domain="nowhere.com") is None


async def test_company_search_per_item_error_returns_none(monkeypatch):
    # A miss comes back as HTTP 200 with {"error": {...}} in place of the
    # result object, not a non-200 status.
    await _capture(monkeypatch, _Response(200, {"results": [{"error": {"code": "NOT_FOUND"}}]}))
    client = LushaClient()
    assert await client.company_search_enrich(domain="nowhere.com") is None


async def test_contact_search_wraps_in_array_and_requests_email_reveal(monkeypatch):
    captured = await _capture(monkeypatch, _Response(200, {"results": [
        {"firstName": "Jane", "emails": [{"email": "jane@acme.com"}]},
    ]}))
    client = LushaClient()
    contact = await client.contact_search_enrich("Jane", "Doe", "acme.com")
    assert captured["json"] == {
        "contacts": [{"firstName": "Jane", "lastName": "Doe", "companyDomain": "acme.com"}],
        "reveal": ["emails"],
    }
    assert contact["emails"][0]["email"] == "jane@acme.com"


async def test_contact_search_not_found_returns_none(monkeypatch):
    await _capture(monkeypatch, _Response(200, {"results": [{"error": {"code": "NOT_FOUND"}}]}))
    client = LushaClient()
    assert await client.contact_search_enrich("Jane", "Doe", "acme.com") is None


async def test_contact_search_billing_block_returns_none(monkeypatch):
    await _capture(monkeypatch, _Response(402, {}))
    client = LushaClient()
    assert await client.contact_search_enrich("Jane", "Doe", "acme.com") is None
