"""標準出力への配信 (--dry-run)。"""

from __future__ import annotations

import sys
from typing import TextIO

from ..models import Digest
from ..render import preview
from .base import Deliverer, DeliveryResult


class ConsoleDeliverer(Deliverer):
    """送信せず内容を表示する。実運用前の確認用。"""

    channel = "console"

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def deliver(self, digest: Digest) -> DeliveryResult:
        self.stream.write(preview(digest))
        self.stream.write("\n")
        return DeliveryResult(self.channel, delivered=True, message_count=len(digest))
