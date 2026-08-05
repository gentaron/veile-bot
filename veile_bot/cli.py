"""コマンドラインインタフェース.

    python -m veile_bot run --dry-run
    python -m veile_bot run --out digests/2026-08-05.md
    python -m veile_bot sources
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import Config, ConfigError
from .delivery import ConsoleDeliverer, Deliverer, LineDeliverer
from .pipeline import RunResult, run
from .render import render_markdown
from .sources import build_sources
from .store import NullStore, SeenStore

logger = logging.getLogger("veile_bot")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DELIVERY_FAILED = 2


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veile-bot",
        description="AI ツール / リポジトリ / モデルの日次ダイジェストを LINE に配信する",
    )
    parser.add_argument("--version", action="version", version=f"veile-bot {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="デバッグログを出す")

    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="ダイジェストを生成して配信する")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="LINE に送らず標準出力に表示する (状態も更新しない)",
    )
    run_parser.add_argument("--no-llm", action="store_true", help="Claude を使わず抽出要約にする")
    run_parser.add_argument("--no-state", action="store_true", help="既配信の記録を無視する")
    run_parser.add_argument("--limit", type=int, metavar="N", help="配信件数の上限")
    run_parser.add_argument(
        "--sources", metavar="A,B", help="使用するソース (カンマ区切り)"
    )
    run_parser.add_argument(
        "--out", type=Path, metavar="PATH", help="Markdown アーカイブの出力先"
    )

    sub.add_parser("sources", help="利用可能なソースを表示する")
    return parser


def _apply_overrides(config: Config, args: argparse.Namespace) -> Config:
    """CLI フラグで設定を上書きする (環境変数より CLI が優先)。"""
    if getattr(args, "limit", None):
        config = dataclasses.replace(config, max_items=args.limit)
    if getattr(args, "sources", None):
        selected = tuple(s.strip() for s in args.sources.split(",") if s.strip())
        config = dataclasses.replace(config, sources=selected)
    if getattr(args, "no_llm", False):
        config = dataclasses.replace(config, llm=dataclasses.replace(config.llm, enabled=False))
    return config


def _deliverers(config: Config, dry_run: bool) -> list[Deliverer]:
    if dry_run:
        return [ConsoleDeliverer()]
    return [
        LineDeliverer(
            config.line,
            timeout=config.http_timeout,
            retries=config.http_retries,
        )
    ]


def _write_archive(path: Path, result: RunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(result.digest), encoding="utf-8")
    logger.info("wrote archive: %s", path)


def _report(result: RunResult) -> int:
    if result.is_empty:
        print("新着なし (候補 " f"{result.collected} 件はすべて既配信または閾値未満)")
        return EXIT_OK

    for delivery in result.deliveries:
        status = "OK" if delivery.delivered else "FAILED"
        detail = f" — {delivery.detail}" if delivery.detail else ""
        print(f"[{status}] {delivery.channel}: {delivery.message_count} message(s){detail}")

    return EXIT_OK if result.delivered else EXIT_DELIVERY_FAILED


def cmd_run(args: argparse.Namespace) -> int:
    config = _apply_overrides(Config.from_env(), args)

    if not args.dry_run and not config.line.is_configured:
        raise ConfigError(
            "LINE の認証情報が未設定です。"
            "LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を設定するか --dry-run を使ってください。"
        )

    store = (
        NullStore()
        if (args.no_state or args.dry_run)
        else SeenStore(config.state_path, config.seen_ttl_days)
    )

    result = run(
        config,
        _deliverers(config, args.dry_run),
        store=store,
        persist=not args.dry_run,
    )

    if args.out and not result.is_empty:
        _write_archive(args.out, result)

    return _report(result)


def cmd_sources(_: argparse.Namespace) -> int:
    config = dataclasses.replace(
        Config.from_env(),
        sources=("github_trending", "huggingface", "note", "seed"),
    )
    for source in build_sources(config):
        enabled = "有効" if source.name in Config.from_env().sources else "無効"
        doc = (type(source).__doc__ or "").strip().splitlines()[0]
        print(f"{source.name:<18} [{enabled}] {doc}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    handlers = {"run": cmd_run, "sources": cmd_sources}
    try:
        return handlers[args.command](args)
    except ConfigError as exc:
        print(f"設定エラー: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover
        print("中断しました", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:
        logger.exception("unhandled error")
        print(f"エラー: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
