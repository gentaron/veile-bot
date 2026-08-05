"""ソースの共通インタフェース。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import ClassVar

from ..config import Config
from ..models import DigestItem


class SourceError(RuntimeError):
    """ソースの設定不備・取得失敗。"""


class Source(ABC):
    """1 つの情報源。

    ``fetch`` は例外を投げてよい。呼び出し側 (:func:`veile_bot.sources.collect`)
    が捕捉して他ソースの取得を続行する。
    """

    name: ClassVar[str]

    def __init__(self, config: Config) -> None:
        self.config = config

    @abstractmethod
    def fetch(self) -> Iterable[DigestItem]:
        """配信候補を返す。"""

    def __repr__(self) -> str:  # pragma: no cover - デバッグ用
        return f"<{type(self).__name__} name={self.name!r}>"
