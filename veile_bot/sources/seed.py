"""手元のキュレーション済みカタログを読み込むソース.

ネットワークが死んでいてもダイジェストを 0 件にしないための保険であり、
外部フィードに載らない「人が選んだ」項目を混ぜるための口でもある。

このカタログの中身は一次情報ではないため、全項目に ``provenance`` を付けて
配信時に出所が分かるようにしている。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from ..config import Config
from ..models import DigestItem, make_item_id
from .base import Source, SourceError

logger = logging.getLogger(__name__)

_DEFAULT_RESOURCE = "seed_catalog.json"


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_catalog(payload: Mapping[str, Any]) -> list[DigestItem]:
    """カタログ JSON を :class:`DigestItem` の列に変換する。"""
    provenance = str(payload.get("provenance", "手動キュレーション"))
    collected_at = _parse_date(payload.get("collected_at"))

    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list):
        raise SourceError("seed カタログの items が配列ではありません")

    items: list[DigestItem] = []
    for entry in raw_items:
        if not isinstance(entry, Mapping):
            continue
        title = entry.get("title")
        url = entry.get("url")
        if not isinstance(title, str) or not isinstance(url, str):
            continue
        raw_key = entry.get("key")
        key = raw_key if isinstance(raw_key, str) and raw_key else title
        tags = tuple(str(t) for t in entry.get("tags", []) if isinstance(t, str))

        items.append(
            DigestItem(
                id=make_item_id("seed", key),
                source="seed",
                title=title,
                url=url,
                summary=str(entry.get("summary", "")),
                tags=("curated", *tags),
                metrics={"curation": float(entry.get("curation", 0.5))},
                published_at=_parse_date(entry.get("published_at")) or collected_at,
                provenance=provenance,
            )
        )
    return items


class SeedCatalogSource(Source):
    """コンストラクタで渡されたパス、無ければパッケージ同梱の JSON を読む。"""

    name = "seed"

    def __init__(self, config: Config, path: Path | None = None) -> None:
        super().__init__(config)
        self.path = path

    def _read(self) -> Mapping[str, Any]:
        if self.path is not None:
            raw = self.path.read_text(encoding="utf-8")
        else:
            raw = (
                resources.files("veile_bot.data").joinpath(_DEFAULT_RESOURCE).read_text("utf-8")
            )
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise SourceError("seed カタログの形式が不正です")
        return payload

    def fetch(self) -> Iterable[DigestItem]:
        return parse_catalog(self._read())
