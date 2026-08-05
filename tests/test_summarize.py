from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from veile_bot.config import LLMConfig
from veile_bot.models import ScoredItem
from veile_bot.summarize import (
    ClaudeSummarizer,
    ExtractiveSummarizer,
    FallbackSummarizer,
    SummarizerError,
    build_summarizer,
    guess_category,
)


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClient:
    """`client.messages.stream(...)` だけを模した最小のダブル。"""

    def __init__(self, payload=None, *, stop_reason="end_turn", raises=None):
        self.payload = payload
        self.stop_reason = stop_reason
        self.raises = raises
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        message = SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=text)],
        )
        return _Stream(message)


@pytest.fixture
def entries(item_factory):
    return [
        ScoredItem(item=item_factory(title="o/agent", summary="agent framework"), score=1.0),
        ScoredItem(item=item_factory(title="o/model", summary="llm weights"), score=0.9),
    ]


def test_extractive_summarizer_covers_every_item(entries):
    highlights, intro = ExtractiveSummarizer().summarize(entries)
    assert set(highlights) == {entry.id for entry in entries}
    assert "2 件" in intro


def test_guess_category_uses_tags(item_factory):
    agent = ScoredItem(item=item_factory(title="x", tags=("agent",)), score=1)
    unknown = ScoredItem(item=item_factory(title="x", summary="園芸"), score=1)
    assert guess_category(agent) == "エージェント"
    assert guess_category(unknown) == "その他"


def test_claude_summarizer_parses_structured_output(entries):
    payload = {
        "intro": "本日は 2 件",
        "items": [
            {
                "id": entries[0].id,
                "headline": "自律エージェント基盤",
                "body": "本文",
                "why_it_matters": "運用が楽になる",
                "category": "エージェント",
            }
        ],
    }
    client = FakeClient(payload)
    highlights, intro = ClaudeSummarizer(LLMConfig(), client=client).summarize(entries)

    assert intro == "本日は 2 件"
    assert highlights[entries[0].id].headline == "自律エージェント基盤"
    assert highlights[entries[0].id].generated_by == "claude"


def test_claude_summarizer_request_shape(entries):
    client = FakeClient({"intro": "", "items": []})
    ClaudeSummarizer(LLMConfig(model="claude-opus-5", effort="high"), client=client).summarize(
        entries
    )

    call = client.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"]["effort"] == "high"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    # 候補はプロンプト末尾（キャッシュされるプレフィックスの後ろ）に置く。
    assert entries[0].id in call["messages"][0]["content"]


def test_claude_summarizer_drops_hallucinated_ids(entries):
    payload = {
        "intro": "x",
        "items": [
            {
                "id": "does-not-exist",
                "headline": "h",
                "body": "b",
                "why_it_matters": "w",
                "category": "モデル",
            }
        ],
    }
    highlights, _ = ClaudeSummarizer(LLMConfig(), client=FakeClient(payload)).summarize(entries)
    assert highlights == {}


def test_claude_summarizer_raises_on_refusal(entries):
    client = FakeClient({"intro": "", "items": []}, stop_reason="refusal")
    with pytest.raises(SummarizerError, match="拒否"):
        ClaudeSummarizer(LLMConfig(), client=client).summarize(entries)


def test_claude_summarizer_raises_on_bad_json(entries):
    with pytest.raises(SummarizerError, match="JSON"):
        ClaudeSummarizer(LLMConfig(), client=FakeClient("not json")).summarize(entries)


def test_fallback_summarizer_recovers_from_api_failure(entries):
    broken = ClaudeSummarizer(LLMConfig(), client=FakeClient(raises=RuntimeError("503")))
    highlights, _ = FallbackSummarizer(broken).summarize(entries)

    assert set(highlights) == {entry.id for entry in entries}
    assert all(h.generated_by == "extractive" for h in highlights.values())


def test_fallback_summarizer_fills_partial_results(entries):
    payload = {
        "intro": "x",
        "items": [
            {
                "id": entries[0].id,
                "headline": "h",
                "body": "b",
                "why_it_matters": "w",
                "category": "モデル",
            }
        ],
    }
    primary = ClaudeSummarizer(LLMConfig(), client=FakeClient(payload))
    highlights, _ = FallbackSummarizer(primary).summarize(entries)

    assert highlights[entries[0].id].generated_by == "claude"
    assert highlights[entries[1].id].generated_by == "extractive"


def test_build_summarizer_respects_disabled_flag():
    assert isinstance(build_summarizer(LLMConfig(enabled=False)), ExtractiveSummarizer)
    assert isinstance(build_summarizer(LLMConfig(enabled=True)), FallbackSummarizer)


def test_summarize_empty_input_short_circuits():
    highlights, intro = ClaudeSummarizer(LLMConfig(), client=FakeClient(None)).summarize([])
    assert (highlights, intro) == ({}, "")
