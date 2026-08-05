from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from veile_bot.config import Config, ConfigError
from veile_bot.store import NullStore, SeenStore


def test_store_roundtrip(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore(path).load()
    store.mark(["a", "b"])
    store.save()

    reloaded = SeenStore(path).load()
    assert reloaded.has_seen("a")
    assert reloaded.has_seen("b")
    assert not reloaded.has_seen("c")


def test_store_prunes_expired_entries(tmp_path):
    path = tmp_path / "seen.json"
    stale = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    recent = datetime.now(UTC).isoformat()
    path.write_text(
        json.dumps({"version": 1, "seen": {"old": stale, "new": recent}}), encoding="utf-8"
    )

    store = SeenStore(path, ttl_days=21).load()
    assert not store.has_seen("old")
    assert store.has_seen("new")


def test_store_recovers_from_corrupt_file(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{ not json", encoding="utf-8")

    store = SeenStore(path).load()
    assert len(store) == 0
    store.mark(["x"])
    store.save()
    assert SeenStore(path).load().has_seen("x")


def test_store_ignores_unparsable_timestamps(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"seen": {"a": "yesterday", "b": 42}}), encoding="utf-8")
    assert len(SeenStore(path).load()) == 0


def test_null_store_never_persists(tmp_path):
    store = NullStore()
    store.mark(["a"])
    store.save()
    assert not store.has_seen("a")
    assert not (tmp_path / "seen.json").exists()


def test_config_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "  token  ")
    monkeypatch.setenv("LINE_USER_ID", "U1")
    monkeypatch.setenv("VEILE_MAX_ITEMS", "3")
    monkeypatch.setenv("VEILE_SOURCES", "seed, huggingface ")
    monkeypatch.setenv("VEILE_LLM_ENABLED", "false")

    config = Config.from_env()
    assert config.line.channel_access_token == "token"
    assert config.line.is_configured
    assert config.max_items == 3
    assert config.sources == ("seed", "huggingface")
    assert config.llm.enabled is False


def test_config_treats_blank_env_as_unset(monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "   ")
    monkeypatch.delenv("LINE_USER_ID", raising=False)
    config = Config.from_env()
    assert config.line.channel_access_token is None
    assert not config.line.is_configured


def test_config_rejects_non_numeric(monkeypatch):
    monkeypatch.setenv("VEILE_MAX_ITEMS", "たくさん")
    with pytest.raises(ConfigError):
        Config.from_env()
