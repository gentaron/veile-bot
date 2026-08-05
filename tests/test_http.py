from __future__ import annotations

import pytest

from veile_bot.http import HttpError, _ensure_http_url, _retry_delay


@pytest.mark.parametrize("url", ["https://example.com/x", "http://example.com"])
def test_http_schemes_allowed(url):
    _ensure_http_url(url)  # 例外が出なければ合格


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com", "/etc/passwd"])
def test_other_schemes_rejected(url):
    with pytest.raises(HttpError, match="許可されない"):
        _ensure_http_url(url)


def test_retry_after_header_wins():
    assert _retry_delay("5", attempt=3, base=2.0) == 5.0


def test_retry_after_is_capped():
    assert _retry_delay("99999", attempt=0, base=2.0) == 60.0


def test_retry_after_garbage_falls_back_to_backoff():
    delay = _retry_delay("soon", attempt=2, base=2.0)
    assert 4.0 <= delay <= 4.5


def test_backoff_grows_with_attempt():
    early = _retry_delay(None, attempt=0, base=2.0)
    late = _retry_delay(None, attempt=4, base=2.0)
    assert late > early


def test_backoff_is_capped():
    assert _retry_delay(None, attempt=50, base=2.0) == 30.0
