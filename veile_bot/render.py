"""ダイジェストを配信形式に変換する.

LINE の Flex Message、プレーンテキスト、Markdown の 3 形式。
Flex はカルーセル 12 バブル / 全体 50KB という API 制限があるので、
超えそうな場合は末尾から落として必ず送れる形にする。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from .models import Digest, Highlight, ScoredItem

MAX_BUBBLES = 10
MAX_FLEX_BYTES = 45_000  # 公式上限 50KB に対する安全マージン
MAX_TEXT_CHARS = 4_900  # 公式上限 5000 文字

_SOURCE_LABEL = {
    "github_trending": "GitHub Trending",
    "huggingface": "Hugging Face",
    "note": "note",
    "seed": "キュレーション",
}

_CATEGORY_COLOR = {
    "エージェント": "#4F46E5",
    "モデル": "#0F766E",
    "開発ツール": "#B45309",
    "インフラ": "#9333EA",
    "その他": "#475569",
}


def source_label(source: str) -> str:
    return _SOURCE_LABEL.get(source, source)


def format_metrics(item: ScoredItem) -> str:
    """バブル下部に出す短い指標行。"""
    metrics = item.item.metrics
    parts: list[str] = []
    if metrics.get("stars_period"):
        parts.append(f"★+{int(metrics['stars_period']):,}/日")
    if metrics.get("stars"):
        parts.append(f"★{int(metrics['stars']):,}")
    if metrics.get("likes"):
        parts.append(f"♥{int(metrics['likes']):,}")
    if metrics.get("downloads"):
        parts.append(f"DL {int(metrics['downloads']):,}")
    return " / ".join(parts)


# ----------------------------------------------------------------- Flex


def _text_node(text: str, **props: Any) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text, "wrap": True}
    node.update(props)
    return node


def build_bubble(entry: ScoredItem, highlight: Highlight) -> dict[str, Any]:
    """1 件分のバブル。"""
    body_contents: list[dict[str, Any]] = [
        _text_node(highlight.headline or entry.item.title, weight="bold", size="md"),
        _text_node(entry.item.title, size="xxs", color="#94A3B8"),
        _text_node(highlight.body, size="sm", color="#334155", margin="md"),
    ]

    if highlight.why_it_matters:
        body_contents.append(
            _text_node(f"→ {highlight.why_it_matters}", size="xs", color="#0F766E", margin="md")
        )

    metrics = format_metrics(entry)
    if metrics:
        body_contents.append(_text_node(metrics, size="xs", color="#64748B", margin="md"))

    if entry.item.provenance:
        body_contents.append(
            _text_node("※ 未検証の伝聞情報", size="xxs", color="#B45309", margin="sm")
        )

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": _CATEGORY_COLOR.get(highlight.category, "#475569"),
            "paddingAll": "10px",
            "contents": [
                _text_node(highlight.category, size="xs", color="#FFFFFF", weight="bold"),
                _text_node(
                    source_label(entry.item.source),
                    size="xxs",
                    color="#E2E8F0",
                    align="end",
                ),
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "none",
            "contents": body_contents,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "link",
                    "height": "sm",
                    "action": {"type": "uri", "label": "開く", "uri": entry.item.url},
                }
            ],
        },
    }


def build_flex_message(digest: Digest) -> dict[str, Any] | None:
    """カルーセル 1 通。項目が無ければ ``None``。"""
    entries = list(digest.items)[:MAX_BUBBLES]
    if not entries:
        return None

    bubbles = [build_bubble(entry, digest.highlight_for(entry)) for entry in entries]

    message = {
        "type": "flex",
        "altText": _alt_text(digest),
        "contents": {"type": "carousel", "contents": bubbles},
    }

    # 50KB 制限に収まるまで末尾から削る。
    while len(json.dumps(message, ensure_ascii=False).encode("utf-8")) > MAX_FLEX_BYTES:
        bubbles.pop()
        if not bubbles:
            return None
        message["contents"] = {"type": "carousel", "contents": bubbles}

    return message


def _alt_text(digest: Digest) -> str:
    head = ", ".join(entry.item.title for entry in list(digest.items)[:3])
    return f"今日の AI ダイジェスト {len(digest)} 件: {head}"[:400]


# ----------------------------------------------------------------- テキスト


def _header_line(generated_at: datetime) -> str:
    return f"☀️ {generated_at:%Y-%m-%d} の AI ダイジェスト"


def render_text(digest: Digest) -> str:
    """Flex 非対応クライアント / dry-run 用のプレーンテキスト。"""
    lines: list[str] = [_header_line(digest.generated_at)]
    if digest.intro:
        lines.append(digest.intro)
    lines.append("")

    for index, entry in enumerate(digest.items, start=1):
        highlight = digest.highlight_for(entry)
        lines.append(f"{index}. [{highlight.category}] {highlight.headline}")
        if highlight.body:
            lines.append(f"   {highlight.body}")
        if highlight.why_it_matters:
            lines.append(f"   → {highlight.why_it_matters}")
        metrics = format_metrics(entry)
        if metrics:
            lines.append(f"   {metrics}")
        if entry.item.provenance:
            lines.append("   ※ 未検証の伝聞情報")
        lines.append(f"   {entry.item.url}")
        lines.append("")

    text = "\n".join(lines).rstrip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[: MAX_TEXT_CHARS - 1].rstrip() + "…"
    return text


def render_markdown(digest: Digest) -> str:
    """アーカイブ用。リポジトリにコミットして履歴を残せる形式。"""
    lines: list[str] = [
        f"# {digest.generated_at:%Y-%m-%d} AI ダイジェスト",
        "",
    ]
    if digest.intro:
        lines += [digest.intro, ""]

    for entry in digest.items:
        highlight = digest.highlight_for(entry)
        lines.append(f"## [{highlight.headline}]({entry.item.url})")
        lines.append("")
        lines.append(
            f"`{highlight.category}` · {source_label(entry.item.source)} · score {entry.score:.3f}"
        )
        lines.append("")
        if highlight.body:
            lines += [highlight.body, ""]
        if highlight.why_it_matters:
            lines += [f"**なぜ重要か**: {highlight.why_it_matters}", ""]
        metrics = format_metrics(entry)
        if metrics:
            lines += [f"指標: {metrics}", ""]
        if entry.item.provenance:
            lines += [f"> 出所: {entry.item.provenance}", ""]
        lines += [f"<sub>選出理由: {' / '.join(entry.reasons)}</sub>", ""]

    return "\n".join(lines).rstrip() + "\n"


def build_messages(digest: Digest) -> list[dict[str, Any]]:
    """LINE push に渡すメッセージ列 (最大 5 通)。"""
    intro = _header_line(digest.generated_at)
    if digest.intro:
        intro = f"{intro}\n{digest.intro}"

    messages: list[dict[str, Any]] = [{"type": "text", "text": intro[:MAX_TEXT_CHARS]}]
    flex = build_flex_message(digest)
    if flex is not None:
        messages.append(flex)
    return messages


def preview(digest: Digest) -> str:
    """人間がターミナルで読む用。"""
    body = render_text(digest)
    sources: Sequence[str] = [entry.item.source for entry in digest.items]
    footer = f"\n\n-- {len(digest)} 件 / ソース: {', '.join(sorted(set(sources)))}"
    return body + footer
