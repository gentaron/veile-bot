from __future__ import annotations

from datetime import UTC, datetime

import pytest

from veile_bot.config import Config, LineConfig, LLMConfig
from veile_bot.models import DigestItem, make_item_id

NOW = datetime(2026, 8, 5, 9, 0, tzinfo=UTC)


@pytest.fixture
def config() -> Config:
    return Config(
        line=LineConfig(channel_access_token="token", user_id="U123"),
        llm=LLMConfig(enabled=False),
        sources=("seed",),
        interests=("agent", "llm", "ローカル"),
        max_items=3,
        candidate_limit=20,
        novelty_bonus=0.25,
    )


@pytest.fixture
def item_factory():
    def make(
        *,
        source: str = "github_trending",
        title: str = "owner/repo",
        url: str | None = None,
        summary: str = "",
        tags: tuple[str, ...] = (),
        metrics: dict[str, float] | None = None,
        published_at: datetime | None = None,
        provenance: str | None = None,
    ) -> DigestItem:
        return DigestItem(
            id=make_item_id(source, title),
            source=source,
            title=title,
            url=url or f"https://github.com/{title}",
            summary=summary,
            tags=tags,
            metrics=metrics or {},
            published_at=published_at,
            provenance=provenance,
        )

    return make
