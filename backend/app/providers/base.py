"""Shared async HTTP client with retry/backoff on 429/5xx and simple pacing."""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

log = logging.getLogger(__name__)

RETRYABLE = {429, 500, 502, 503, 529}
MAX_RETRY_DELAY = 30.0  # a server's Retry-After can be absurd (e.g. a daily
                        # quota reset, seen as 86400s from Cerebras) — never
                        # block a worker task on it; cap and let the caller's
                        # own retry/backoff loop (or the user) decide instead


class BaseClient:
    base_url: str = ""

    def __init__(self, max_retries: int = 4, requests_per_second: float = 3.0):
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
        self._max_retries = max_retries
        self._min_interval = 1.0 / requests_per_second
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _pace(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._min_interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = asyncio.get_event_loop().time()

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await self._pace()
            try:
                resp = await self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
                await asyncio.sleep(min(2 ** attempt + random.random(), 30))
                continue
            if resp.status_code in RETRYABLE and attempt < self._max_retries:
                delay = min(2 ** attempt + random.random(), MAX_RETRY_DELAY)
                retry_after = resp.headers.get("retry-after")
                if retry_after:
                    try:
                        delay = min(float(retry_after), MAX_RETRY_DELAY)
                    except ValueError:
                        pass  # non-numeric (e.g. HTTP-date) — keep the backoff delay
                log.warning("HTTP %s from %s — retrying in %.1fs", resp.status_code, url, delay)
                await asyncio.sleep(delay)
                continue
            return resp
        raise last_exc or RuntimeError(f"request to {url} failed after retries")

    async def close(self) -> None:
        await self._client.aclose()
