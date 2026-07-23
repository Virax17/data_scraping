"""CerebrasClient round-robins judge calls across every configured key, so
free-tier throughput scales with key count instead of sharing one 5 req/min
budget."""

import json

from app.providers import cerebras_client as cerebras_module
from app.providers.cerebras_client import CerebrasClient, _SingleKeyClient


class _FakeConfig:
    def __init__(self, keys):
        self.cerebras_api_keys = keys


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content": json.dumps({"verdicts": []})}}]}


async def test_round_robins_across_multiple_keys(monkeypatch):
    monkeypatch.setattr(cerebras_module, "get_config",
                        lambda: _FakeConfig(["key-a", "key-b", "key-c"]))
    used_keys = []

    async def fake_request(self, method, url, **kwargs):
        used_keys.append(self._client.headers["Authorization"])
        return _FakeResponse()

    monkeypatch.setattr(_SingleKeyClient, "request", fake_request)

    client = CerebrasClient()
    assert len(client._clients) == 3
    for _ in range(6):
        await client.judge_completion("model", "system", "payload")

    assert used_keys == [
        "Bearer key-a", "Bearer key-b", "Bearer key-c",
        "Bearer key-a", "Bearer key-b", "Bearer key-c",
    ]


async def test_single_key_still_works(monkeypatch):
    monkeypatch.setattr(cerebras_module, "get_config", lambda: _FakeConfig(["only-key"]))

    async def fake_request(self, method, url, **kwargs):
        return _FakeResponse()

    monkeypatch.setattr(_SingleKeyClient, "request", fake_request)

    client = CerebrasClient()
    assert len(client._clients) == 1
    result = await client.judge_completion("model", "system", "payload")
    assert result == {"verdicts": []}


async def test_no_keys_raises(monkeypatch):
    monkeypatch.setattr(cerebras_module, "get_config", lambda: _FakeConfig([]))
    try:
        CerebrasClient()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
