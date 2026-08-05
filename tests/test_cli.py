from __future__ import annotations

import pytest

from veile_bot import cli


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """CLI テストは常に「認証情報なし・seed のみ・LLM なし」から始める。"""
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINE_USER_ID", raising=False)
    monkeypatch.setenv("VEILE_SOURCES", "seed")
    monkeypatch.setenv("VEILE_LLM_ENABLED", "0")
    monkeypatch.setenv("VEILE_STATE_PATH", str(tmp_path / "seen.json"))


def test_dry_run_prints_digest_without_credentials(capsys):
    assert cli.main(["run", "--dry-run", "--limit", "2"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "AI ダイジェスト" in out
    assert "console: 2 message(s)" in out


def test_dry_run_does_not_write_state(tmp_path, capsys):
    cli.main(["run", "--dry-run"])
    capsys.readouterr()
    assert not (tmp_path / "seen.json").exists()


def test_run_without_credentials_is_a_config_error(capsys):
    assert cli.main(["run"]) == cli.EXIT_ERROR
    assert "設定エラー" in capsys.readouterr().err


def test_out_flag_writes_markdown(tmp_path, capsys):
    target = tmp_path / "digests" / "today.md"
    assert cli.main(["run", "--dry-run", "--out", str(target)]) == cli.EXIT_OK
    capsys.readouterr()
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("# ")


def test_sources_command_lists_registry(capsys):
    assert cli.main(["sources"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    for name in ("github_trending", "huggingface", "note", "seed"):
        assert name in out


def test_unknown_source_is_reported(capsys):
    assert cli.main(["run", "--dry-run", "--sources", "nope"]) == cli.EXIT_ERROR
    assert "未知のソース" in capsys.readouterr().err
