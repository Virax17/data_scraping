"""get_config() merges CEREBRAS_API_KEY + CEREBRAS_API_KEYS into one deduped
list that CerebrasClient round-robins across."""

import pytest

from app.config import get_config


@pytest.fixture(autouse=True)
def _restore_real_config():
    """get_config() is lru_cached at module scope — leaving it holding a
    test-only config would leak into unrelated tests that run afterward."""
    yield
    get_config.cache_clear()
    get_config()


def _reload_config(monkeypatch, **env):
    for key in ("CEREBRAS_API_KEY", "CEREBRAS_API_KEYS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_config.cache_clear()
    return get_config()


def test_single_key_only(monkeypatch):
    cfg = _reload_config(monkeypatch, CEREBRAS_API_KEY="key-a")
    assert cfg.cerebras_api_keys == ["key-a"]


def test_primary_plus_extra_keys(monkeypatch):
    cfg = _reload_config(monkeypatch, CEREBRAS_API_KEY="key-a",
                         CEREBRAS_API_KEYS="key-b,key-c,key-d")
    assert cfg.cerebras_api_keys == ["key-a", "key-b", "key-c", "key-d"]


def test_extra_keys_deduped_against_primary(monkeypatch):
    cfg = _reload_config(monkeypatch, CEREBRAS_API_KEY="key-a",
                         CEREBRAS_API_KEYS="key-a, key-b")
    assert cfg.cerebras_api_keys == ["key-a", "key-b"]


def test_no_keys_configured(monkeypatch):
    cfg = _reload_config(monkeypatch)
    assert cfg.cerebras_api_keys == []


def test_whitespace_and_empty_entries_ignored(monkeypatch):
    cfg = _reload_config(monkeypatch, CEREBRAS_API_KEY="key-a",
                         CEREBRAS_API_KEYS=" key-b ,, key-c ,")
    assert cfg.cerebras_api_keys == ["key-a", "key-b", "key-c"]
