"""環境変数ベースの設定.

秘密情報はリポジトリに置かない。すべて環境変数 (ローカルは .env) から読む。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_INTERESTS: tuple[str, ...] = (
    "agent",
    "エージェント",
    "llm",
    "claude",
    "mcp",
    "rag",
    "local",
    "ローカル",
    "inference",
    "推論",
    "coding",
    "code review",
    "automation",
    "自動化",
    "memory",
    "quantization",
    "moe",
    "cli",
    "developer tools",
)

DEFAULT_SOURCES: tuple[str, ...] = ("github_trending", "huggingface", "note", "seed")


class ConfigError(ValueError):
    """設定が不足・不正なときに送出する。"""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - 入力ミス時のみ
        raise ConfigError(f"{name} は整数で指定してください: {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover
        raise ConfigError(f"{name} は数値で指定してください: {raw!r}") from exc


def _env_list(name: str, default: Sequence[str]) -> tuple[str, ...]:
    raw = _env(name)
    if raw is None:
        return tuple(default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class LineConfig:
    """LINE Messaging API の認証情報。"""

    channel_access_token: str | None
    user_id: str | None
    api_base: str = "https://api.line.me"

    @property
    def is_configured(self) -> bool:
        return bool(self.channel_access_token and self.user_id)

    def require(self) -> tuple[str, str]:
        if not self.channel_access_token:
            raise ConfigError(
                "LINE_CHANNEL_ACCESS_TOKEN が未設定です。"
                "--dry-run で動作確認するか、環境変数を設定してください。"
            )
        if not self.user_id:
            raise ConfigError("LINE_USER_ID が未設定です。")
        return self.channel_access_token, self.user_id


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Claude による要約生成の設定。"""

    enabled: bool = True
    model: str = "claude-opus-5"
    effort: str = "high"
    max_tokens: int = 16000
    api_key: str | None = None

    @property
    def usable(self) -> bool:
        # api_key が無くても ant のプロファイル認証で動くため、ここでは
        # enabled だけを見る。実際の可否は summarize 側で判定する。
        return self.enabled


@dataclass(frozen=True, slots=True)
class Config:
    """アプリ全体の設定。"""

    line: LineConfig
    llm: LLMConfig
    sources: tuple[str, ...] = DEFAULT_SOURCES
    interests: tuple[str, ...] = DEFAULT_INTERESTS
    note_feeds: tuple[str, ...] = ("https://note.com/humble_bobcat51/rss",)
    max_items: int = 8
    candidate_limit: int = 60
    min_score: float = 0.0
    freshness_half_life_hours: float = 36.0
    novelty_bonus: float = 0.25
    state_path: Path = Path("state/seen.json")
    seen_ttl_days: int = 21
    http_timeout: float = 15.0
    http_retries: int = 3
    source_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "github_trending": 1.0,
            "huggingface": 0.9,
            "note": 0.75,
            "seed": 0.6,
        }
    )

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            line=LineConfig(
                channel_access_token=_env("LINE_CHANNEL_ACCESS_TOKEN"),
                user_id=_env("LINE_USER_ID"),
                api_base=_env("LINE_API_BASE", "https://api.line.me") or "https://api.line.me",
            ),
            llm=LLMConfig(
                enabled=_env_bool("VEILE_LLM_ENABLED", True),
                model=_env("VEILE_LLM_MODEL", "claude-opus-5") or "claude-opus-5",
                effort=_env("VEILE_LLM_EFFORT", "high") or "high",
                max_tokens=_env_int("VEILE_LLM_MAX_TOKENS", 16000),
                api_key=_env("ANTHROPIC_API_KEY"),
            ),
            sources=_env_list("VEILE_SOURCES", DEFAULT_SOURCES),
            interests=_env_list("VEILE_INTERESTS", DEFAULT_INTERESTS),
            note_feeds=_env_list("VEILE_NOTE_FEEDS", ("https://note.com/humble_bobcat51/rss",)),
            max_items=_env_int("VEILE_MAX_ITEMS", 8),
            candidate_limit=_env_int("VEILE_CANDIDATE_LIMIT", 60),
            min_score=_env_float("VEILE_MIN_SCORE", 0.0),
            freshness_half_life_hours=_env_float("VEILE_FRESHNESS_HALF_LIFE_HOURS", 36.0),
            novelty_bonus=_env_float("VEILE_NOVELTY_BONUS", 0.25),
            state_path=Path(_env("VEILE_STATE_PATH", "state/seen.json") or "state/seen.json"),
            seen_ttl_days=_env_int("VEILE_SEEN_TTL_DAYS", 21),
            http_timeout=_env_float("VEILE_HTTP_TIMEOUT", 15.0),
            http_retries=_env_int("VEILE_HTTP_RETRIES", 3),
        )
