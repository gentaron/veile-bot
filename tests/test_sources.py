from __future__ import annotations

import json

import pytest

from veile_bot.sources import collect
from veile_bot.sources.base import Source, SourceError
from veile_bot.sources.github_trending import parse_trending
from veile_bot.sources.huggingface import _to_item
from veile_bot.sources.note_rss import parse_feed
from veile_bot.sources.seed import SeedCatalogSource, parse_catalog

TRENDING_HTML = """
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/citrolabs/ego-lite">
      <span class="text-normal">citrolabs / </span>ego-lite
    </a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">
    Fast browser built for AI agents &amp; humans
  </p>
  <div class="f6 color-fg-muted mt-2">
    <span itemprop="programmingLanguage">TypeScript</span>
    <a href="/citrolabs/ego-lite/stargazers" class="Link--muted">4,312</a>
    <a href="/citrolabs/ego-lite/forks" class="Link--muted">201</a>
    <span class="d-inline-block float-sm-right">893 stars today</span>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a href="/alibaba/open-code-review">alibaba / open-code-review</a></h2>
  <div class="f6 color-fg-muted mt-2">
    <a href="/alibaba/open-code-review/stargazers">1,024</a>
  </div>
</article>
"""


def test_parse_trending_extracts_fields():
    items = parse_trending(TRENDING_HTML)
    assert [item.title for item in items] == ["citrolabs/ego-lite", "alibaba/open-code-review"]

    first = items[0]
    assert first.url == "https://github.com/citrolabs/ego-lite"
    assert first.summary == "Fast browser built for AI agents & humans"
    assert first.language == "TypeScript"
    assert first.metrics == {"stars": 4312.0, "forks": 201.0, "stars_period": 893.0}
    assert "typescript" in first.tags
    assert first.author == "citrolabs"


def test_parse_trending_tolerates_missing_optional_fields():
    second = parse_trending(TRENDING_HTML)[1]
    assert second.summary == ""
    assert second.language is None
    assert second.metrics["stars_period"] == 0.0


def test_parse_trending_returns_empty_on_unknown_markup():
    assert parse_trending("<div>completely different</div>") == []


def test_huggingface_item_mapping():
    item = _to_item(
        {
            "id": "deepgrove/Maple-Preview",
            "likes": 320,
            "downloads": 41000,
            "trendingScore": 37.5,
            "pipeline_tag": "text-generation",
            "tags": ["text-generation", "ternary"],
            "lastModified": "2026-08-05T02:11:00.000Z",
        }
    )
    assert item is not None
    assert item.url == "https://huggingface.co/deepgrove/Maple-Preview"
    assert item.author == "deepgrove"
    assert item.metrics["trending"] == 37.5
    assert item.published_at is not None and item.published_at.tzinfo is not None


def test_huggingface_item_requires_id():
    assert _to_item({"likes": 5}) is None


def test_parse_feed_reads_rss():
    rss = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>PenguinHarness 徹底解説</title>
        <link>https://note.com/humble_bobcat51/n/n622a78202682</link>
        <description>&lt;p&gt;エージェントがエージェントを作る&lt;/p&gt;</description>
        <pubDate>Tue, 04 Aug 2026 22:10:00 +0900</pubDate>
      </item>
    </channel></rss>"""
    items = parse_feed(rss, "https://note.com/humble_bobcat51/rss")
    assert len(items) == 1
    assert items[0].title == "PenguinHarness 徹底解説"
    assert "エージェント" in items[0].summary
    assert items[0].published_at is not None


def test_parse_feed_ignores_broken_xml():
    assert parse_feed("<rss><channel>", "u") == []


def test_seed_catalog_marks_provenance(config):
    items = list(SeedCatalogSource(config).fetch())
    assert items, "同梱カタログが空"
    assert all(item.provenance for item in items)
    assert all(item.source == "seed" for item in items)
    assert all("curated" in item.tags for item in items)


def test_parse_catalog_skips_malformed_entries():
    payload = json.loads(
        json.dumps(
            {
                "provenance": "test",
                "items": [
                    {"title": "ok", "url": "https://example.com"},
                    {"title": "no url"},
                    "garbage",
                ],
            }
        )
    )
    assert [item.title for item in parse_catalog(payload)] == ["ok"]


def test_parse_catalog_rejects_non_list_items():
    with pytest.raises(SourceError):
        parse_catalog({"items": {}})


def test_collect_survives_a_failing_source(config, item_factory):
    class Boom(Source):
        name = "boom"

        def fetch(self):
            raise RuntimeError("down")

    class Fine(Source):
        name = "fine"

        def fetch(self):
            return [item_factory(title="o/r")]

    items = collect([Boom(config), Fine(config)])
    assert [item.title for item in items] == ["o/r"]
