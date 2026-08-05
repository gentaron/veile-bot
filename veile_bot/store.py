"""配信済みアイテムの永続化.

同じリポジトリ/モデルを毎日送りつけないための最小限の状態管理。
JSON 1 ファイルで十分な規模なので DB は使わない。
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1


class SeenStore:
    """``id -> 最終配信時刻`` の単純なストア。"""

    def __init__(self, path: Path, ttl_days: int = 21) -> None:
        self.path = path
        self.ttl = timedelta(days=ttl_days)
        self._seen: dict[str, datetime] = {}

    # ------------------------------------------------------------------ io

    def load(self) -> SeenStore:
        if not self.path.exists():
            return self
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # 状態ファイルの破損で配信を止める価値はない。空から作り直す。
            logger.warning("state file unreadable (%s), starting fresh: %s", self.path, exc)
            return self

        entries = raw.get("seen", {}) if isinstance(raw, dict) else {}
        for item_id, stamp in entries.items():
            parsed = _parse_ts(stamp)
            if parsed is not None:
                self._seen[item_id] = parsed
        self._prune()
        return self

    def save(self) -> None:
        self._prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _SCHEMA_VERSION,
            "updated_at": _now().isoformat(),
            "seen": {k: v.isoformat() for k, v in sorted(self._seen.items())},
        }
        # 途中で落ちても壊れたファイルを残さないよう atomic replace。
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            tmp_path = Path(handle.name)
        tmp_path.replace(self.path)

    # --------------------------------------------------------------- query

    def has_seen(self, item_id: str) -> bool:
        return item_id in self._seen

    def mark(self, item_ids: Iterable[str]) -> None:
        now = _now()
        for item_id in item_ids:
            self._seen[item_id] = now

    def __len__(self) -> int:
        return len(self._seen)

    # -------------------------------------------------------------- helper

    def _prune(self) -> None:
        cutoff = _now() - self.ttl
        self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}


class NullStore(SeenStore):
    """`--no-state` 用。読み書きしない。"""

    def __init__(self) -> None:
        super().__init__(Path("/dev/null"), ttl_days=0)

    def load(self) -> NullStore:
        return self

    def save(self) -> None:
        return None

    def has_seen(self, item_id: str) -> bool:
        return False

    def mark(self, item_ids: Iterable[str]) -> None:
        return None


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
