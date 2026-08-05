"""Hugging Face Hub のトレンドモデルを取得する.

こちらは公開 JSON API があるのでスクレイプ不要。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from .. import http
from ..models import DigestItem, make_item_id
from .base import Source

_API = "https://huggingface.co/api/models"


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _to_item(payload: Mapping[str, Any]) -> DigestItem | None:
    model_id = payload.get("id") or payload.get("modelId")
    if not isinstance(model_id, str) or not model_id:
        return None

    tags = tuple(str(t) for t in payload.get("tags", []) if isinstance(t, str))[:12]
    pipeline = payload.get("pipeline_tag")
    author = model_id.split("/", 1)[0] if "/" in model_id else None

    return DigestItem(
        id=make_item_id("huggingface", model_id),
        source="huggingface",
        title=model_id,
        url=f"https://huggingface.co/{model_id}",
        summary=f"{pipeline} モデル" if isinstance(pipeline, str) else "",
        tags=("huggingface", "model", *tags),
        metrics={
            "likes": float(payload.get("likes") or 0),
            "downloads": float(payload.get("downloads") or 0),
            "trending": float(payload.get("trendingScore") or 0),
        },
        published_at=_parse_ts(payload.get("lastModified") or payload.get("createdAt")),
        author=author,
    )


class HuggingFaceTrendingSource(Source):
    """trendingScore 降順で新着モデルを取得する。"""

    name = "huggingface"

    def fetch(self) -> Iterable[DigestItem]:
        url = f"{_API}?sort=trendingScore&direction=-1&limit=30&full=false"
        payload = http.get_json(
            url,
            timeout=self.config.http_timeout,
            retries=self.config.http_retries,
        )
        if not isinstance(payload, list):
            return []
        items = (_to_item(entry) for entry in payload if isinstance(entry, Mapping))
        return [item for item in items if item is not None]
