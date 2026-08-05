"""配信候補の採点・重複排除・選抜.

素朴な加重和にしてある。ここを凝るより「なぜ選ばれたか」を
:attr:`ScoredItem.reasons` で説明できることを優先した — 出力が納得いかない
ときに調整すべきつまみが一目で分かる。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .config import Config
from .models import DigestItem, ScoredItem
from .store import SeenStore

# 重み。合計 1.0。
W_MOMENTUM = 0.42
W_AFFINITY = 0.33
W_FRESHNESS = 0.25

# 各指標を 0..1 に潰すときの「これくらいで満点」基準値。
_MOMENTUM_REFERENCE: Mapping[str, Mapping[str, float]] = {
    "github_trending": {"stars_period": 600.0, "stars": 20000.0},
    "huggingface": {"trending": 40.0, "likes": 400.0, "downloads": 100000.0},
    "seed": {"curation": 1.0},
}
_DEFAULT_MOMENTUM = 0.45


def _log_norm(value: float, reference: float) -> float:
    """0..1 に圧縮する。大きな数字の差を潰しつつ順序は保つ。"""
    if value <= 0 or reference <= 0:
        return 0.0
    return min(math.log1p(value) / math.log1p(reference), 1.0)


def momentum(item: DigestItem) -> float:
    """勢い。ソースごとに意味のある指標が違うので個別に正規化する。"""
    references = _MOMENTUM_REFERENCE.get(item.source)
    if not references:
        return _DEFAULT_MOMENTUM

    scores = [
        _log_norm(float(item.metrics.get(key, 0.0)), reference)
        for key, reference in references.items()
    ]
    if not scores:
        return _DEFAULT_MOMENTUM
    # 主指標を重く見る: 最大値 7 割 + 平均 3 割。
    return 0.7 * max(scores) + 0.3 * (sum(scores) / len(scores))


def _haystack(item: DigestItem) -> str:
    parts = [item.title, item.summary, " ".join(item.tags), item.language or ""]
    return " ".join(parts).lower()


def affinity(item: DigestItem, interests: Sequence[str]) -> tuple[float, tuple[str, ...]]:
    """興味プロファイルとの一致度と、一致したキーワード。"""
    if not interests:
        return 0.5, ()
    text = _haystack(item)
    hits = tuple(kw for kw in interests if kw.lower() in text)
    if not hits:
        return 0.0, ()
    # 3 語一致でほぼ満点。語数が増えるほど伸びは鈍る。
    return min(len(hits) / 3.0, 1.0), hits


def freshness(item: DigestItem, half_life_hours: float, now: datetime) -> float:
    """新しさ。半減期による指数減衰。時刻不明のものは中立値。"""
    if item.published_at is None:
        return 0.55
    age_hours = max((now - item.published_at).total_seconds() / 3600.0, 0.0)
    if half_life_hours <= 0:
        return 1.0
    return float(0.5 ** (age_hours / half_life_hours))


def score_item(item: DigestItem, config: Config, now: datetime) -> ScoredItem:
    """1 件を採点する。"""
    mom = momentum(item)
    aff, hits = affinity(item, config.interests)
    fresh = freshness(item, config.freshness_half_life_hours, now)
    weight = config.source_weights.get(item.source, 0.7)

    score = weight * (W_MOMENTUM * mom + W_AFFINITY * aff + W_FRESHNESS * fresh)

    reasons: list[str] = [
        f"勢い {mom:.2f}",
        f"関心度 {aff:.2f}" + (f" ({', '.join(hits[:4])})" if hits else ""),
        f"新しさ {fresh:.2f}",
    ]

    if item.published_at is not None and (now - item.published_at).total_seconds() <= 86400:
        score += config.novelty_bonus
        reasons.append(f"24h 以内の新着 +{config.novelty_bonus:.2f}")

    return ScoredItem(item=item, score=round(score, 4), reasons=tuple(reasons))


def canonical_key(item: DigestItem) -> str:
    """異なるソースから来た同じ対象をまとめるためのキー。"""
    parts = urlsplit(item.url)
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/").lower()
    if host == "github.com":
        # /owner/repo より深い階層は同じリポジトリとして扱う。
        segments = [seg for seg in path.split("/") if seg]
        if len(segments) >= 2:
            return f"github.com/{segments[0]}/{segments[1]}"
    if host and path:
        return f"{host}{path}"
    return item.title.strip().lower()


def dedupe(scored: Iterable[ScoredItem]) -> list[ScoredItem]:
    """同一対象は最高スコアの 1 件に畳む。"""
    best: dict[str, ScoredItem] = {}
    for entry in scored:
        key = canonical_key(entry.item)
        current = best.get(key)
        if current is None or entry.score > current.score:
            best[key] = entry
    return list(best.values())


def select(
    items: Iterable[DigestItem],
    config: Config,
    store: SeenStore,
    *,
    now: datetime | None = None,
) -> list[ScoredItem]:
    """採点 → 既配信除外 → 重複排除 → 上位 N 件。"""
    moment = now or datetime.now(UTC)

    fresh_items = [item for item in items if not store.has_seen(item.id)]
    scored = [score_item(item, config, moment) for item in fresh_items]
    scored = [entry for entry in scored if entry.score >= config.min_score]
    scored.sort(key=lambda entry: (-entry.score, entry.item.title))

    # 下位は畳む前に切り落とす。重複排除は上位候補にだけ効けば十分で、
    # 要約に回す件数を抑えるほど LLM コストが下がる。
    scored = dedupe(scored[: config.candidate_limit])
    scored.sort(key=lambda entry: (-entry.score, entry.item.title))
    return scored[: config.max_items]
