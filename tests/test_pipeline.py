from __future__ import annotations

import dataclasses
import io
import json

import pytest

from veile_bot.config import Config, ConfigError, LineConfig
from veile_bot.delivery import ConsoleDeliverer
from veile_bot.delivery.base import Deliverer, DeliveryError, DeliveryResult
from veile_bot.models import Digest
from veile_bot.pipeline import run
from veile_bot.store import SeenStore
from veile_bot.summarize import ExtractiveSummarizer

from .conftest import NOW


class RecordingDeliverer(Deliverer):
    channel = "recording"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.digests: list[Digest] = []

    def deliver(self, digest: Digest) -> DeliveryResult:
        if self.fail:
            raise DeliveryError("boom")
        self.digests.append(digest)
        return DeliveryResult(self.channel, delivered=True, message_count=len(digest))


@pytest.fixture
def seed_config(config: Config, tmp_path) -> Config:
    return dataclasses.replace(config, sources=("seed",), state_path=tmp_path / "seen.json")


def test_run_delivers_and_persists_state(seed_config):
    store = SeenStore(seed_config.state_path)
    deliverer = RecordingDeliverer()

    result = run(
        seed_config,
        [deliverer],
        store=store,
        summarizer=ExtractiveSummarizer(),
        now=NOW,
    )

    assert result.delivered
    assert len(result.digest) == seed_config.max_items
    assert seed_config.state_path.exists()

    saved = json.loads(seed_config.state_path.read_text(encoding="utf-8"))
    assert set(saved["seen"]) == {entry.id for entry in result.digest.items}


def test_second_run_skips_already_delivered(seed_config):
    first = run(
        seed_config,
        [RecordingDeliverer()],
        store=SeenStore(seed_config.state_path),
        summarizer=ExtractiveSummarizer(),
        now=NOW,
    )
    second = run(
        seed_config,
        [RecordingDeliverer()],
        store=SeenStore(seed_config.state_path),
        summarizer=ExtractiveSummarizer(),
        now=NOW,
    )

    first_ids = {entry.id for entry in first.digest.items}
    second_ids = {entry.id for entry in second.digest.items}
    assert first_ids and second_ids
    assert first_ids.isdisjoint(second_ids)


def test_failed_delivery_does_not_mark_state(seed_config):
    store = SeenStore(seed_config.state_path)
    result = run(
        seed_config,
        [RecordingDeliverer(fail=True)],
        store=store,
        summarizer=ExtractiveSummarizer(),
        now=NOW,
    )

    assert not result.delivered
    assert result.deliveries[0].detail == "boom"
    assert not seed_config.state_path.exists()


def test_partial_delivery_still_persists(seed_config):
    result = run(
        seed_config,
        [RecordingDeliverer(fail=True), RecordingDeliverer()],
        store=SeenStore(seed_config.state_path),
        summarizer=ExtractiveSummarizer(),
        now=NOW,
    )
    assert result.delivered
    assert seed_config.state_path.exists()


def test_console_deliverer_writes_preview(seed_config):
    stream = io.StringIO()
    result = run(
        seed_config,
        [ConsoleDeliverer(stream)],
        store=SeenStore(seed_config.state_path),
        summarizer=ExtractiveSummarizer(),
        now=NOW,
    )
    output = stream.getvalue()
    assert "AI ダイジェスト" in output
    assert result.digest.items[0].item.title in output


def test_line_config_require_raises_when_missing():
    with pytest.raises(ConfigError):
        LineConfig(channel_access_token=None, user_id="U1").require()
    with pytest.raises(ConfigError):
        LineConfig(channel_access_token="t", user_id=None).require()
