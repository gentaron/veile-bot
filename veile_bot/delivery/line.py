"""LINE Messaging API への push 配信.

line-bot-sdk は使わない。使うのは push エンドポイント 1 本だけで、
SDK を挟むと再試行や冪等キーの制御がしにくいため。
"""

from __future__ import annotations

import logging
import uuid

from .. import http
from ..config import LineConfig
from ..models import Digest
from ..render import build_messages
from .base import Deliverer, DeliveryError, DeliveryResult

logger = logging.getLogger(__name__)

_PUSH_PATH = "/v2/bot/message/push"


class LineDeliverer(Deliverer):
    """設定されたユーザーへ push する。"""

    channel = "line"

    def __init__(self, config: LineConfig, *, timeout: float = 15.0, retries: int = 3) -> None:
        self.config = config
        self.timeout = timeout
        self.retries = retries

    def deliver(self, digest: Digest) -> DeliveryResult:
        token, user_id = self.config.require()
        messages = build_messages(digest)
        if not messages:
            return DeliveryResult(self.channel, delivered=False, detail="送信対象がありません")

        payload = {"to": user_id, "messages": messages}
        headers = {
            "Authorization": f"Bearer {token}",
            # 再試行が二重投稿にならないようにする (LINE 側で 24 時間デデュープ)。
            "X-Line-Retry-Key": str(uuid.uuid4()),
        }

        try:
            http.post_json(
                f"{self.config.api_base}{_PUSH_PATH}",
                payload,
                headers=headers,
                timeout=self.timeout,
                retries=self.retries,
            )
        except http.HttpError as exc:
            raise DeliveryError(f"LINE への push に失敗しました: {exc}") from exc

        logger.info("pushed %d message(s) to LINE", len(messages))
        return DeliveryResult(self.channel, delivered=True, message_count=len(messages))
