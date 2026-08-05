"""ダイジェストを構成するドメインモデル.

すべて不変オブジェクト。取得 (sources) → 採点 (ranking) → 要約 (summarize)
→ 描画 (render) → 配信 (delivery) の各段でこの型だけを受け渡す。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def make_item_id(source: str, key: str) -> str:
    """ソースをまたいで安定する重複判定キー.

    URL やタイトルの表記ゆれで別物と判定されないよう、正規化した slug の
    ハッシュを使う。同じリポジトリが GitHub Trending と note 紹介の両方から
    流れてきた場合も、呼び出し側が同じ ``key`` を渡せば同一視できる。
    """
    slug = _SLUG_RE.sub("-", key.strip().lower()).strip("-")
    digest = hashlib.sha256(f"{source}:{slug}".encode()).hexdigest()[:16]
    return f"{source}:{slug[:48]}:{digest[:8]}"


@dataclass(frozen=True, slots=True)
class DigestItem:
    """配信候補 1 件。ソース層が返す生の情報。"""

    id: str
    source: str
    title: str
    url: str
    summary: str = ""
    tags: tuple[str, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)
    published_at: datetime | None = None
    author: str | None = None
    language: str | None = None
    provenance: str | None = None
    """一次情報でない場合の出所 (例: ユーザー提供のキュレーション)。"""

    def with_summary(self, summary: str) -> DigestItem:
        return replace(self, summary=summary)


@dataclass(frozen=True, slots=True)
class ScoredItem:
    """採点済みの配信候補。"""

    item: DigestItem
    score: float
    reasons: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.item.id


@dataclass(frozen=True, slots=True)
class Highlight:
    """LLM が生成した日本語の解説。生成に失敗した場合は抽出要約で代替する。"""

    item_id: str
    headline: str
    body: str
    category: str = "その他"
    why_it_matters: str = ""
    generated_by: str = "extractive"


@dataclass(frozen=True, slots=True)
class Digest:
    """1 回の配信単位。"""

    generated_at: datetime
    items: Sequence[ScoredItem]
    highlights: Mapping[str, Highlight]
    intro: str = ""

    def highlight_for(self, item: ScoredItem) -> Highlight:
        found = self.highlights.get(item.id)
        if found is not None:
            return found
        return Highlight(
            item_id=item.id,
            headline=item.item.title,
            body=item.item.summary,
        )

    def __len__(self) -> int:
        return len(self.items)
