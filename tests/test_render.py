from __future__ import annotations

import json

from veile_bot.models import Digest, Highlight, ScoredItem
from veile_bot.render import (
    MAX_BUBBLES,
    build_flex_message,
    build_messages,
    format_metrics,
    render_markdown,
    render_text,
)

from .conftest import NOW


def _digest(entries, highlights=None, intro="今日は 2 件"):
    return Digest(
        generated_at=NOW,
        items=entries,
        highlights=highlights or {},
        intro=intro,
    )


def _scored(item, score=1.0):
    return ScoredItem(item=item, score=score, reasons=("勢い 0.90",))


def test_flex_message_shape(item_factory):
    entry = _scored(item_factory(title="o/r", metrics={"stars_period": 900}))
    digest = _digest(
        [entry],
        {
            entry.id: Highlight(
                item_id=entry.id,
                headline="エージェント専用ブラウザ",
                body="本文",
                category="エージェント",
                why_it_matters="トークン節約",
            )
        },
    )

    message = build_flex_message(digest)
    assert message is not None
    assert message["type"] == "flex"
    assert message["contents"]["type"] == "carousel"
    bubble = message["contents"]["contents"][0]
    assert bubble["footer"]["contents"][0]["action"]["uri"] == "https://github.com/o/r"
    rendered = json.dumps(message, ensure_ascii=False)
    assert "エージェント専用ブラウザ" in rendered
    assert "★+900/日" in rendered


def test_flex_message_is_none_when_empty():
    assert build_flex_message(_digest([])) is None


def test_flex_message_caps_bubble_count(item_factory):
    entries = [_scored(item_factory(title=f"o/r{i}")) for i in range(MAX_BUBBLES + 5)]
    message = build_flex_message(_digest(entries))
    assert message is not None
    assert len(message["contents"]["contents"]) == MAX_BUBBLES


def test_flex_message_shrinks_to_fit_size_limit(item_factory):
    huge = "あ" * 4000
    entries = [
        _scored(item_factory(title=f"o/r{i}", summary=huge)) for i in range(MAX_BUBBLES)
    ]
    highlights = {
        entry.id: Highlight(item_id=entry.id, headline=huge, body=huge) for entry in entries
    }
    message = build_flex_message(_digest(entries, highlights))
    assert message is not None
    size = len(json.dumps(message, ensure_ascii=False).encode("utf-8"))
    assert size <= 45_000
    assert len(message["contents"]["contents"]) < MAX_BUBBLES


def test_unverified_items_are_labelled(item_factory):
    entry = _scored(item_factory(source="seed", title="噂のツール", provenance="ユーザー提供"))
    digest = _digest([entry])
    assert "未検証" in json.dumps(build_flex_message(digest), ensure_ascii=False)
    assert "未検証" in render_text(digest)
    assert "ユーザー提供" in render_markdown(digest)


def test_render_text_contains_urls_and_intro(item_factory):
    entry = _scored(item_factory(title="o/r"))
    text = render_text(_digest([entry]))
    assert "今日は 2 件" in text
    assert "https://github.com/o/r" in text


def test_render_text_respects_length_limit(item_factory):
    entries = [_scored(item_factory(title=f"o/r{i}", summary="あ" * 500)) for i in range(30)]
    highlights = {
        entry.id: Highlight(item_id=entry.id, headline="あ" * 200, body="い" * 400)
        for entry in entries
    }
    assert len(render_text(_digest(entries, highlights))) <= 4_900


def test_render_markdown_includes_reasons(item_factory):
    entry = _scored(item_factory(title="o/r"))
    md = render_markdown(_digest([entry]))
    assert md.startswith("# 2026-08-05")
    assert "選出理由" in md
    assert "(https://github.com/o/r)" in md


def test_build_messages_returns_intro_and_flex(item_factory):
    messages = build_messages(_digest([_scored(item_factory(title="o/r"))]))
    assert [m["type"] for m in messages] == ["text", "flex"]


def test_build_messages_without_items_has_no_flex():
    assert [m["type"] for m in build_messages(_digest([]))] == ["text"]


def test_format_metrics_skips_zero(item_factory):
    assert format_metrics(_scored(item_factory(title="o/r", metrics={"stars": 0}))) == ""
    assert "★1,000" in format_metrics(_scored(item_factory(title="o/r", metrics={"stars": 1000})))
