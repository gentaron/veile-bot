"""標準ライブラリだけの HTTP クライアント.

依存を増やさないための薄いラッパ。指数バックオフ再試行、gzip 展開、
プロキシ環境変数の尊重 (urllib のデフォルト挙動) を担当する。
"""

from __future__ import annotations

import gzip
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENT = "veile-bot/2.0 (+https://github.com/gentaron/veile-bot)"

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class HttpError(RuntimeError):
    """再試行しても回復しなかった HTTP 失敗。"""

    def __init__(self, url: str, status: int | None, message: str) -> None:
        super().__init__(f"{url} -> {status or 'no response'}: {message}")
        self.url = url
        self.status = status


def _ensure_http_url(url: str) -> None:
    """http/https 以外を弾く。

    フィード URL は設定 (環境変数) 由来なので、``file:`` などのスキームで
    ローカルファイルを読ませられないようにする。
    """
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise HttpError(url, None, f"許可されないスキームです: {scheme or '(なし)'}")


def _decode(raw: bytes, encoding_header: str | None) -> str:
    if encoding_header and "gzip" in encoding_header.lower():
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 15.0,
    retries: int = 3,
    backoff_base: float = 1.5,
) -> str:
    """テキストレスポンスを返す。失敗時は :class:`HttpError`。

    ``retries`` は再試行回数 (合計試行回数は ``retries + 1``)。429 は
    ``Retry-After`` を尊重する。
    """
    merged: dict[str, str] = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip",
    }
    if headers:
        merged.update(headers)

    _ensure_http_url(url)

    last_status: int | None = None
    last_message = "unknown error"

    for attempt in range(retries + 1):
        # S310 抑制の根拠: _ensure_http_url で http/https のみに限定済み。
        req = urllib.request.Request(url, data=body, headers=merged, method=method)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return _decode(resp.read(), resp.headers.get("Content-Encoding"))
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            last_message = exc.reason or str(exc)
            if exc.code not in RETRYABLE_STATUS or attempt == retries:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise HttpError(url, exc.code, f"{last_message} {detail}".strip()) from exc
            delay = _retry_delay(exc.headers.get("Retry-After"), attempt, backoff_base)
        except urllib.error.URLError as exc:
            last_status = None
            last_message = str(exc.reason)
            if attempt == retries:
                raise HttpError(url, None, last_message) from exc
            delay = _retry_delay(None, attempt, backoff_base)
        except TimeoutError as exc:
            last_status = None
            last_message = "timeout"
            if attempt == retries:
                raise HttpError(url, None, last_message) from exc
            delay = _retry_delay(None, attempt, backoff_base)

        logger.warning(
            "http retry %s/%s url=%s status=%s reason=%s sleep=%.1fs",
            attempt + 1,
            retries,
            url,
            last_status,
            last_message,
            delay,
        )
        time.sleep(delay)

    raise HttpError(url, last_status, last_message)  # pragma: no cover - ループ上到達不能


def _retry_delay(retry_after: str | None, attempt: int, base: float) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(base**attempt + random.uniform(0, 0.5), 30.0)  # noqa: S311 - jitter 用途


def get_json(url: str, **kwargs: Any) -> Any:
    """JSON を取得してパースする。"""
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("Accept", "application/json")
    text = request(url, headers=headers, **kwargs)
    return json.loads(text)


def post_json(url: str, payload: Any, **kwargs: Any) -> str:
    """JSON を POST する。"""
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("Content-Type", "application/json")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return request(url, method="POST", headers=headers, body=body, **kwargs)
