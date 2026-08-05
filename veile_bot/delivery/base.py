"""配信先の共通インタフェース。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import Digest


class DeliveryError(RuntimeError):
    """配信の失敗。"""


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """配信結果。CLI の終了コードと状態保存の判断に使う。"""

    channel: str
    delivered: bool
    message_count: int = 0
    detail: str = ""


class Deliverer(Protocol):
    """配信先。"""

    channel: str

    def deliver(self, digest: Digest) -> DeliveryResult:
        """ダイジェストを送る。"""
        ...
