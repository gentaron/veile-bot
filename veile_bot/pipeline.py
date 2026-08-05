"""取得 → 採点 → 要約 → 配信のオーケストレーション.

CLI からも Actions からもテストからも、入口はここ 1 つ。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from .config import Config
from .delivery.base import Deliverer, DeliveryError, DeliveryResult
from .models import Digest
from .ranking import select
from .sources import build_sources, collect
from .store import SeenStore
from .summarize import Summarizer, build_summarizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunResult:
    """1 回の実行結果。"""

    digest: Digest
    deliveries: Sequence[DeliveryResult]
    collected: int

    @property
    def delivered(self) -> bool:
        return any(result.delivered for result in self.deliveries)

    @property
    def is_empty(self) -> bool:
        return len(self.digest) == 0


def build_digest(
    config: Config,
    store: SeenStore,
    *,
    summarizer: Summarizer | None = None,
    now: datetime | None = None,
) -> tuple[Digest, int]:
    """ダイジェストと、採点前に集まった候補数を返す。"""
    moment = now or datetime.now(UTC)

    items = collect(build_sources(config))
    logger.info("collected %d candidate(s)", len(items))

    selected = select(items, config, store, now=moment)
    logger.info("selected %d item(s)", len(selected))

    engine = summarizer or build_summarizer(config.llm)
    highlights, intro = engine.summarize(selected)

    digest = Digest(
        generated_at=moment,
        items=selected,
        highlights=highlights,
        intro=intro,
    )
    return digest, len(items)


def run(
    config: Config,
    deliverers: Sequence[Deliverer],
    *,
    store: SeenStore,
    summarizer: Summarizer | None = None,
    now: datetime | None = None,
    persist: bool = True,
) -> RunResult:
    """ダイジェストを作って配信し、成功したら既配信として記録する。"""
    store.load()
    digest, collected = build_digest(config, store, summarizer=summarizer, now=now)

    results: list[DeliveryResult] = []
    if len(digest) == 0:
        logger.info("no new items today; skipping delivery")
        return RunResult(digest=digest, deliveries=results, collected=collected)

    for deliverer in deliverers:
        try:
            results.append(deliverer.deliver(digest))
        except DeliveryError as exc:
            logger.error("delivery failed channel=%s: %s", deliverer.channel, exc)
            results.append(
                DeliveryResult(deliverer.channel, delivered=False, detail=str(exc))
            )

    # 送れていないものを「配信済み」にすると翌日以降に取りこぼす。
    if persist and any(result.delivered for result in results):
        store.mark(entry.id for entry in digest.items)
        store.save()

    return RunResult(digest=digest, deliveries=results, collected=collected)
