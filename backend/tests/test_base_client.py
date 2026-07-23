"""BaseClient retry delay must never blindly trust a server's Retry-After —
Cerebras was observed returning 86400 (a day) on an ordinary 429, which used
to sleep a worker task for 24 hours instead of retrying reasonably."""

import asyncio

from app.providers.base import BaseClient, MAX_RETRY_DELAY


class _Response:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


async def _run_with_responses(monkeypatch, responses):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    client = BaseClient.__new__(BaseClient)
    client._max_retries = len(responses) - 1
    client._min_interval = 0
    client._lock = asyncio.Lock()
    client._last_request = 0.0

    responses_iter = iter(responses)

    async def fake_request(method, url, **kwargs):
        return next(responses_iter)

    class _FakeHttpxClient:
        request = staticmethod(fake_request)

    client._client = _FakeHttpxClient()

    result = await client.request("GET", "/x")
    return result, sleeps


async def test_absurd_retry_after_is_capped(monkeypatch):
    responses = [
        _Response(429, {"retry-after": "86400"}),
        _Response(200),
    ]
    result, sleeps = await _run_with_responses(monkeypatch, responses)
    assert result.status_code == 200
    assert sleeps == [MAX_RETRY_DELAY]


async def test_non_numeric_retry_after_falls_back_to_backoff(monkeypatch):
    responses = [
        _Response(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        _Response(200),
    ]
    result, sleeps = await _run_with_responses(monkeypatch, responses)
    assert result.status_code == 200
    assert 0 <= sleeps[0] <= MAX_RETRY_DELAY


async def test_normal_backoff_without_retry_after_is_capped(monkeypatch):
    responses = [_Response(503) for _ in range(6)] + [_Response(200)]
    result, sleeps = await _run_with_responses(monkeypatch, responses)
    assert result.status_code == 200
    assert all(s <= MAX_RETRY_DELAY for s in sleeps)
