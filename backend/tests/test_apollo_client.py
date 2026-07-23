"""Assert the search-customization params land in the Apollo request body
only when the caller supplies them — no behavior change for existing callers."""

import httpx

from app.providers.apollo_client import ApolloClient


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"people": [], "total_entries": 0}


async def _capture(monkeypatch):
    captured = {}

    async def fake_request(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return _FakeResponse()

    monkeypatch.setattr(ApolloClient, "request", fake_request)
    return captured


async def test_people_search_page_default_body_unchanged(monkeypatch):
    captured = await _capture(monkeypatch)
    client = ApolloClient()
    await client.people_search_page("acme.com", page=2)
    body = captured["json"]
    assert body == {"q_organization_domains_list": ["acme.com"], "page": 2, "per_page": 100}


async def test_people_search_page_with_seniorities(monkeypatch):
    captured = await _capture(monkeypatch)
    client = ApolloClient()
    await client.people_search_page("acme.com", seniorities=["vp", "director"])
    assert captured["json"]["person_seniorities"] == ["vp", "director"]


async def test_people_search_page_with_region_and_filters(monkeypatch):
    captured = await _capture(monkeypatch)
    client = ApolloClient()
    await client.people_search_page(
        "acme.com",
        person_locations=["Houston, United States"],
        organization_locations=["Houston, United States"],
        person_titles=["Maintenance Manager"],
        q_keywords="rotating equipment",
        organization_num_employees_ranges=["51,200"],
    )
    body = captured["json"]
    assert body["person_locations"] == ["Houston, United States"]
    assert body["organization_locations"] == ["Houston, United States"]
    assert body["person_titles"] == ["Maintenance Manager"]
    assert body["q_keywords"] == "rotating equipment"
    assert body["organization_num_employees_ranges"] == ["51,200"]


async def test_people_search_page_no_domain_never_calls_apollo(monkeypatch):
    # Regression: a null q_organization_domains_list entry doesn't error on
    # Apollo's side — it silently returns some unscoped result set, which
    # leaked identical "employees" onto every domain-less company. Must
    # short-circuit locally instead of ever sending the request.
    called = False

    async def fail_if_called(self, method, url, **kwargs):
        nonlocal called
        called = True
        return _FakeResponse()

    monkeypatch.setattr(ApolloClient, "request", fail_if_called)
    client = ApolloClient()
    result = await client.people_search_page(None)
    assert result == {"people": [], "total_entries": 0}
    assert called is False

    result = await client.people_search_page("")
    assert result == {"people": [], "total_entries": 0}
    assert called is False


async def test_people_search_page_surfaces_total_entries(monkeypatch):
    # Regression: Apollo's response has no pagination.total_pages field — it
    # returns a flat total_entries count instead (verified live). The client
    # must surface it so the caller can actually page through results.
    class _Response:
        status_code = 200

        def json(self):
            return {"people": [{"id": "p1"}], "total_entries": 39}

    async def fake_request(self, method, url, **kwargs):
        return _Response()

    monkeypatch.setattr(ApolloClient, "request", fake_request)
    client = ApolloClient()
    result = await client.people_search_page("acme.com")
    assert result["total_entries"] == 39
    assert "pagination" not in result


async def test_people_search_page_empty_filters_omitted(monkeypatch):
    captured = await _capture(monkeypatch)
    client = ApolloClient()
    await client.people_search_page(
        "acme.com", person_locations=[], person_titles=None, q_keywords="",
        organization_num_employees_ranges=[])
    body = captured["json"]
    assert "person_locations" not in body
    assert "person_titles" not in body
    assert "q_keywords" not in body
    assert "organization_num_employees_ranges" not in body
