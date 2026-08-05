"""ダイジェスト本文の生成.

一次実装は Claude (Anthropic SDK) による日本語要約。SDK 未インストール・
認証なし・API 障害のいずれでも配信を止めないよう、抽出要約へフォールバックする。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .config import LLMConfig
from .models import Highlight, ScoredItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたは日本語の技術ニュースレター編集者です。
AI エージェント / LLM / 開発自動化まわりの新着リポジトリ・モデル・記事を、
毎朝 LINE で受け取る読者（個人開発者）向けに短くまとめます。

書き方:
- 各項目は「何ができるか」と「既存手段と何が違うか」を必ず含める。
- headline は 30 文字以内の日本語。体言止めでよい。
- body は 90〜130 文字。誇張表現や「革命的」のような語は使わない。
- why_it_matters は 40 文字以内で、読者にとっての実利を書く。
- category は次から 1 つ選ぶ: エージェント / モデル / 開発ツール / インフラ / その他。
- 入力に無い事実を足さない。数値は入力にあるものだけ使う。
- provenance が付いている項目は未検証の伝聞なので、断定を避け「〜とされる」と書く。

intro は当日のダイジェスト全体を 60 文字以内で俯瞰する一文。"""

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intro": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "headline": {"type": "string"},
                    "body": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "エージェント",
                            "モデル",
                            "開発ツール",
                            "インフラ",
                            "その他",
                        ],
                    },
                },
                "required": ["id", "headline", "body", "why_it_matters", "category"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intro", "items"],
    "additionalProperties": False,
}

_WS_RE = re.compile(r"\s+")


class SummarizerError(RuntimeError):
    """要約生成の失敗。"""


class Summarizer(Protocol):
    """要約器のインタフェース。"""

    def summarize(self, items: Sequence[ScoredItem]) -> tuple[dict[str, Highlight], str]:
        """``(item_id -> Highlight, intro)`` を返す。"""
        ...


# --------------------------------------------------------------------- 抽出


_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("エージェント", ("agent", "エージェント", "mcp", "orchestration")),
    ("モデル", ("model", "llm", "moe", "quantization", "huggingface")),
    ("開発ツール", ("developer tools", "cli", "code review", "coding", "frontend")),
    ("インフラ", ("infra", "serving", "inference", "推論", "vllm")),
)


def guess_category(item: ScoredItem) -> str:
    text = " ".join((item.item.title, item.item.summary, *item.item.tags)).lower()
    for category, keywords in _CATEGORY_HINTS:
        if any(keyword in text for keyword in keywords):
            return category
    return "その他"


def _truncate(text: str, limit: int) -> str:
    cleaned = _WS_RE.sub(" ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


class ExtractiveSummarizer:
    """LLM を使わないフォールバック。ソースの説明文をそのまま整形する。"""

    name = "extractive"

    def summarize(self, items: Sequence[ScoredItem]) -> tuple[dict[str, Highlight], str]:
        highlights = {
            entry.id: Highlight(
                item_id=entry.id,
                headline=_truncate(entry.item.title, 40),
                body=_truncate(entry.item.summary or entry.item.url, 130),
                category=guess_category(entry),
                why_it_matters="",
                generated_by=self.name,
            )
            for entry in items
        }
        intro = f"本日の注目 {len(items)} 件（自動抽出）"
        return highlights, intro


# ---------------------------------------------------------------------- LLM


def _payload_for(entry: ScoredItem) -> dict[str, Any]:
    item = entry.item
    payload: dict[str, Any] = {
        "id": entry.id,
        "title": item.title,
        "url": item.url,
        "source": item.source,
        "description": item.summary,
        "tags": list(item.tags),
        "metrics": {k: v for k, v in item.metrics.items() if v},
    }
    if item.language:
        payload["language"] = item.language
    if item.provenance:
        payload["provenance"] = item.provenance
    return payload


class ClaudeSummarizer:
    """Anthropic SDK 経由で Claude に日本語要約を書かせる。"""

    name = "claude"

    def __init__(self, config: LLMConfig, client: Any | None = None) -> None:
        self.config = config
        self._client = client

    # 遅延 import: LLM を使わない実行で anthropic を必須にしない。
    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - 環境依存
            raise SummarizerError(
                "anthropic SDK が未インストールです (pip install 'veile-bot[llm]')"
            ) from exc

        kwargs: dict[str, Any] = {}
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        # api_key 未指定でも ANTHROPIC_API_KEY / ant のプロファイルから解決される。
        self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def summarize(self, items: Sequence[ScoredItem]) -> tuple[dict[str, Highlight], str]:
        if not items:
            return {}, ""

        client = self._ensure_client()
        user_payload = json.dumps(
            [_payload_for(entry) for entry in items], ensure_ascii=False, indent=2
        )

        try:
            with client.messages.stream(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        # システムプロンプトは固定。項目 JSON は後段なのでキャッシュが効く。
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.config.effort,
                    "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
                },
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "次の候補それぞれについて日本語の紹介文を書いてください。"
                            "id は入力のものをそのまま返してください。\n\n"
                            f"{user_payload}"
                        ),
                    }
                ],
            ) as stream:
                response = stream.get_final_message()
        except Exception as exc:
            raise SummarizerError(f"Claude への要求が失敗しました: {exc}") from exc

        # 安全分類器が拒否した場合、content は空か途中まで。先に stop_reason を見る。
        if getattr(response, "stop_reason", None) == "refusal":
            raise SummarizerError("Claude が生成を拒否しました (stop_reason=refusal)")

        text = next(
            (block.text for block in response.content if getattr(block, "type", "") == "text"),
            None,
        )
        if not text:
            raise SummarizerError("Claude のレスポンスにテキストがありません")

        return self._parse(text, items)

    def _parse(
        self, text: str, items: Sequence[ScoredItem]
    ) -> tuple[dict[str, Highlight], str]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SummarizerError(f"Claude の JSON をパースできません: {exc}") from exc
        if not isinstance(data, Mapping):
            raise SummarizerError("Claude の出力がオブジェクトではありません")

        known = {entry.id for entry in items}
        highlights: dict[str, Highlight] = {}
        for raw in data.get("items", []):
            if not isinstance(raw, Mapping):
                continue
            item_id = raw.get("id")
            if item_id not in known:
                # 幻の id を配信に混ぜない。
                logger.warning("summarizer returned unknown id: %r", item_id)
                continue
            highlights[str(item_id)] = Highlight(
                item_id=str(item_id),
                headline=_truncate(str(raw.get("headline", "")), 40),
                body=_truncate(str(raw.get("body", "")), 160),
                category=str(raw.get("category", "その他")),
                why_it_matters=_truncate(str(raw.get("why_it_matters", "")), 60),
                generated_by=self.name,
            )
        return highlights, _truncate(str(data.get("intro", "")), 80)


class FallbackSummarizer:
    """LLM を試し、失敗したら抽出要約に落とす。"""

    def __init__(self, primary: Summarizer, fallback: Summarizer | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or ExtractiveSummarizer()

    def summarize(self, items: Sequence[ScoredItem]) -> tuple[dict[str, Highlight], str]:
        try:
            highlights, intro = self.primary.summarize(items)
        except SummarizerError as exc:
            logger.warning("LLM 要約に失敗、抽出要約にフォールバックします: %s", exc)
            return self.fallback.summarize(items)

        # 部分的にしか返ってこなかった項目は抽出要約で埋める。
        missing = [entry for entry in items if entry.id not in highlights]
        if missing:
            logger.info("filling %d item(s) with extractive summaries", len(missing))
            filled, _ = self.fallback.summarize(missing)
            highlights.update(filled)
        return highlights, intro


def build_summarizer(config: LLMConfig) -> Summarizer:
    """設定から要約器を組み立てる。"""
    if not config.usable:
        return ExtractiveSummarizer()
    return FallbackSummarizer(ClaudeSummarizer(config))
