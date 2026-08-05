from __future__ import annotations

from datetime import timedelta

from veile_bot.ranking import (
    affinity,
    canonical_key,
    dedupe,
    freshness,
    momentum,
    score_item,
    select,
)
from veile_bot.store import NullStore

from .conftest import NOW


def test_momentum_prefers_higher_daily_stars(item_factory):
    hot = item_factory(title="a/hot", metrics={"stars_period": 900, "stars": 4000})
    warm = item_factory(title="a/warm", metrics={"stars_period": 30, "stars": 4000})
    assert momentum(hot) > momentum(warm)


def test_momentum_is_bounded(item_factory):
    absurd = item_factory(title="a/absurd", metrics={"stars_period": 10**9, "stars": 10**9})
    assert 0.0 <= momentum(absurd) <= 1.0


def test_momentum_defaults_for_sources_without_metrics(item_factory):
    article = item_factory(source="note", title="記事", url="https://note.com/x/n/1")
    assert momentum(article) == 0.45


def test_affinity_matches_japanese_and_english(item_factory):
    item = item_factory(title="x/y", summary="ローカルで動く agent フレームワーク")
    score, hits = affinity(item, ("agent", "ローカル", "無関係"))
    assert score > 0
    assert set(hits) == {"agent", "ローカル"}


def test_affinity_zero_without_hits(item_factory):
    item = item_factory(title="x/y", summary="ガーデニング用のツール")
    score, hits = affinity(item, ("agent",))
    assert (score, hits) == (0.0, ())


def test_freshness_decays_with_half_life(item_factory):
    fresh = item_factory(title="a/fresh", published_at=NOW)
    old = item_factory(title="a/old", published_at=NOW - timedelta(hours=36))
    assert freshness(fresh, 36.0, NOW) == 1.0
    assert abs(freshness(old, 36.0, NOW) - 0.5) < 1e-9


def test_freshness_neutral_when_unknown(item_factory):
    assert freshness(item_factory(title="a/x"), 36.0, NOW) == 0.55


def test_novelty_bonus_applies_only_within_24h(config, item_factory):
    brand_new = score_item(item_factory(title="a/new", published_at=NOW), config, NOW)
    yesterday = score_item(
        item_factory(title="a/old", published_at=NOW - timedelta(hours=48)), config, NOW
    )
    assert any("新着" in reason for reason in brand_new.reasons)
    assert not any("新着" in reason for reason in yesterday.reasons)


def test_canonical_key_collapses_github_subpaths(item_factory):
    a = item_factory(title="o/r", url="https://github.com/o/r")
    b = item_factory(title="o/r stars", url="https://github.com/o/r/stargazers")
    assert canonical_key(a) == canonical_key(b) == "github.com/o/r"


def test_dedupe_keeps_highest_score(config, item_factory):
    strong = score_item(
        item_factory(title="o/r", metrics={"stars_period": 900}, summary="agent"), config, NOW
    )
    weak = score_item(
        item_factory(source="seed", title="o/r", url="https://github.com/o/r"), config, NOW
    )
    result = dedupe([weak, strong])
    assert len(result) == 1
    assert result[0].score == strong.score


def test_select_respects_max_items_and_skips_seen(config, item_factory):
    items = [
        item_factory(title=f"o/repo{i}", metrics={"stars_period": 100 * i}, summary="agent llm")
        for i in range(1, 6)
    ]

    class Seen(NullStore):
        def has_seen(self, item_id: str) -> bool:
            return item_id == items[-1].id

    selected = select(items, config, Seen(), now=NOW)
    assert len(selected) == config.max_items
    assert items[-1].id not in {entry.id for entry in selected}
    scores = [entry.score for entry in selected]
    assert scores == sorted(scores, reverse=True)


def test_select_applies_min_score(config, item_factory):
    import dataclasses

    strict = dataclasses.replace(config, min_score=99.0)
    assert select([item_factory(title="o/r")], strict, NullStore(), now=NOW) == []
