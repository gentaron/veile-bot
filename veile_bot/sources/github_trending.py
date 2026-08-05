"""GitHub Trending から急上昇リポジトリを取得する.

Trending は公式 API を持たないため HTML をパースする。壊れやすい前提で
「取れた分だけ返す」設計にし、1 件も取れなかった場合のみ例外を投げる
(サイレントに 0 件になるのが一番まずい)。
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable

from .. import http
from ..models import DigestItem, make_item_id
from .base import Source, SourceError

logger = logging.getLogger(__name__)

_ARTICLE_RE = re.compile(r'<article class="Box-row">(.*?)</article>', re.DOTALL)
_REPO_RE = re.compile(r'<h2[^>]*>\s*<a[^>]+href="/([^"?#]+)"', re.DOTALL)
_DESC_RE = re.compile(r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', re.DOTALL)
_LANG_RE = re.compile(r'itemprop="programmingLanguage"[^>]*>([^<]+)<')
_STARS_RE = re.compile(r'href="/[^"]+/stargazers"[^>]*>\s*([\d,]+)')
_FORKS_RE = re.compile(r'href="/[^"]+/(?:forks|network/members)"[^>]*>\s*([\d,]+)')
_PERIOD_RE = re.compile(r'float-sm-right[^>]*>\s*([\d,]+)\s+stars?\s+(today|this week|this month)')
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment)).strip()


def _number(match: re.Match[str] | None, group: int = 1) -> float:
    if match is None:
        return 0.0
    try:
        return float(match.group(group).replace(",", ""))
    except (ValueError, IndexError):  # pragma: no cover - HTML 変化時の保険
        return 0.0


def parse_trending(document: str) -> list[DigestItem]:
    """Trending ページの HTML を :class:`DigestItem` の列に変換する。

    純粋関数なので、保存した HTML を使ってテストできる。
    """
    items: list[DigestItem] = []
    for block in _ARTICLE_RE.findall(document):
        repo_match = _REPO_RE.search(block)
        if repo_match is None:
            continue
        full_name = repo_match.group(1).strip().strip("/")
        if full_name.count("/") != 1:
            continue

        desc_match = _DESC_RE.search(block)
        description = _clean(desc_match.group(1)) if desc_match else ""
        lang_match = _LANG_RE.search(block)
        language = _clean(lang_match.group(1)) if lang_match else None
        period_match = _PERIOD_RE.search(block)

        metrics = {
            "stars": _number(_STARS_RE.search(block)),
            "forks": _number(_FORKS_RE.search(block)),
            "stars_period": _number(period_match),
        }

        items.append(
            DigestItem(
                id=make_item_id("github_trending", full_name),
                source="github_trending",
                title=full_name,
                url=f"https://github.com/{full_name}",
                summary=description,
                tags=("github", "trending") + ((language.lower(),) if language else ()),
                metrics=metrics,
                language=language,
                author=full_name.split("/", 1)[0],
            )
        )
    return items


class GitHubTrendingSource(Source):
    """https://github.com/trending をスクレイプする。"""

    name = "github_trending"

    def fetch(self) -> Iterable[DigestItem]:
        url = "https://github.com/trending?since=daily"
        document = http.request(
            url,
            headers={"Accept": "text/html"},
            timeout=self.config.http_timeout,
            retries=self.config.http_retries,
        )
        items = parse_trending(document)
        if not items:
            # HTML 構造が変わったサイン。黙って 0 件にせず気付けるようにする。
            raise SourceError(
                "GitHub Trending から 1 件も抽出できませんでした "
                "(ページ構造が変わった可能性があります)"
            )
        return items
