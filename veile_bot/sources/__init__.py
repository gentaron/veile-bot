"""情報ソース層.

各ソースは :class:`Source` を実装し、失敗しても他ソースを巻き込まない。
1 つ落ちても残りでダイジェストを作れることを優先する。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from ..config import Config
from ..models import DigestItem
from .base import Source, SourceError
from .github_trending import GitHubTrendingSource
from .huggingface import HuggingFaceTrendingSource
from .note_rss import NoteRssSource
from .seed import SeedCatalogSource

logger = logging.getLogger(__name__)

__all__ = [
    "GitHubTrendingSource",
    "HuggingFaceTrendingSource",
    "NoteRssSource",
    "SeedCatalogSource",
    "Source",
    "SourceError",
    "build_sources",
    "collect",
]


def build_sources(config: Config) -> list[Source]:
    """設定で有効化されたソースだけを組み立てる。"""
    registry: dict[str, type[Source]] = {
        GitHubTrendingSource.name: GitHubTrendingSource,
        HuggingFaceTrendingSource.name: HuggingFaceTrendingSource,
        NoteRssSource.name: NoteRssSource,
        SeedCatalogSource.name: SeedCatalogSource,
    }
    unknown = [name for name in config.sources if name not in registry]
    if unknown:
        raise SourceError(
            f"未知のソース: {', '.join(unknown)} (利用可能: {', '.join(sorted(registry))})"
        )
    return [registry[name](config) for name in config.sources]


def collect(sources: Sequence[Source]) -> list[DigestItem]:
    """全ソースを順に叩き、取れたものを連結する。

    1 ソースの失敗は警告に留める — 部分的なダイジェストは無配信より価値がある。
    """
    items: list[DigestItem] = []
    for source in sources:
        try:
            fetched = list(source.fetch())
        except Exception as exc:  # noqa: BLE001 - ソース障害を全体障害にしない
            logger.warning("source %s failed: %s", source.name, exc)
            continue
        logger.info("source %s -> %d items", source.name, len(fetched))
        items.extend(fetched)
    return items
