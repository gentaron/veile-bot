"""note.com などの RSS フィードから紹介記事を取得する.

既定では note.com/humble_bobcat51 (ゆいまる) の RSS を購読する。
``VEILE_NOTE_FEEDS`` にカンマ区切りで任意のフィードを指定できる。
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from .. import http
from ..models import DigestItem, make_item_id
from .base import Source

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _text(node: ElementTree.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", node.text))).strip()


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_feed(document: str, feed_url: str) -> list[DigestItem]:
    """RSS 2.0 / Atom を :class:`DigestItem` の列に変換する。"""
    try:
        root = ElementTree.fromstring(document)  # noqa: S314 - 自分で選んだフィードのみ
    except ElementTree.ParseError as exc:
        logger.warning("feed parse failed url=%s: %s", feed_url, exc)
        return []

    channel = root.find("channel")
    entries = channel.findall("item") if channel is not None else root.findall("item")
    if not entries:  # Atom
        ns = "{http://www.w3.org/2005/Atom}"
        entries = root.findall(f"{ns}entry")

    items: list[DigestItem] = []
    for entry in entries:
        title = _text(entry.find("title")) or _text(
            entry.find("{http://www.w3.org/2005/Atom}title")
        )
        link_node = entry.find("link")
        link = _text(link_node)
        if not link and link_node is not None:
            link = link_node.get("href", "")
        if not link:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.get("href", "") if atom_link is not None else ""
        if not title or not link:
            continue

        description = _text(entry.find("description")) or _text(
            entry.find("{http://www.w3.org/2005/Atom}summary")
        )
        published = _parse_date(
            _text(entry.find("pubDate"))
            or _text(entry.find("{http://www.w3.org/2005/Atom}published"))
        )
        creator = _text(entry.find("{http://purl.org/dc/elements/1.1/}creator")) or None

        items.append(
            DigestItem(
                id=make_item_id("note", link),
                source="note",
                title=title,
                url=link,
                summary=description[:400],
                tags=("note", "article"),
                metrics={},
                published_at=published,
                author=creator,
            )
        )
    return items


class NoteRssSource(Source):
    """設定されたフィードをまとめて取得する。"""

    name = "note"

    def fetch(self) -> Iterable[DigestItem]:
        items: list[DigestItem] = []
        for feed_url in self.config.note_feeds:
            try:
                document = http.request(
                    feed_url,
                    headers={"Accept": "application/rss+xml, application/xml, text/xml"},
                    timeout=self.config.http_timeout,
                    retries=self.config.http_retries,
                )
            except http.HttpError as exc:
                # 1 フィードの失敗で他フィードを落とさない。
                logger.warning("feed fetch failed: %s", exc)
                continue
            items.extend(parse_feed(document, feed_url))
        return items
