"""Tests for vera.doctor — each check mocked."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.doctor import (
    CheckResult,
    CheckStatus,
    check_config_yaml,
    check_env_file,
    check_llm,
    check_notion_databases,
    check_notion_token,
    check_python_version,
    check_state_writable,
    check_telegram_bot,
    check_telegram_chat_id,
    check_user_md,
    print_results,
    run_all_checks,
)


# ─── Individual Checks ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_python_version_ok():
    """Python version check passes on 3.11+."""
    result = await check_python_version()
    assert result.status == CheckStatus.OK


@pytest.mark.asyncio
async def test_env_file_exists(tmp_path, monkeypatch):
    """Env file with required vars returns OK."""
    monkeypatch.chdir(tmp_path)
    env = tmp_path / ".env"
    env.write_text("NOTION_TOKEN=ntnl_test\nANTHROPIC_API_KEY=sk-ant-test\n")

    result = await check_env_file()
    assert result.status == CheckStatus.OK


@pytest.mark.asyncio
async def test_env_file_missing(tmp_path, monkeypatch):
    """Missing .env returns FAIL."""
    monkeypatch.chdir(tmp_path)
    result = await check_env_file()
    assert result.status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_env_file_incomplete(tmp_path, monkeypatch):
    """Env file missing keys returns WARN."""
    monkeypatch.chdir(tmp_path)
    env = tmp_path / ".env"
    env.write_text("NOTION_TOKEN=ntnl_test\n")

    result = await check_env_file()
    assert result.status == CheckStatus.WARN


@pytest.mark.asyncio
async def test_config_yaml_valid(tmp_path, monkeypatch):
    """Valid config.yaml returns OK."""
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text(
        "name: Vera\nlanguage: pt-BR\ntimezone: America/Sao_Paulo\n"
        "backend:\n  type: notion\n  notion:\n    token_env: NOTION_TOKEN\n"
        "llm:\n  default: claude\n  advanced: claude\n"
        "  providers:\n    claude:\n      model: claude-sonnet-4-5-20250929\n"
        "      api_key_env: ANTHROPIC_API_KEY\n"
        "domains:\n  tasks:\n    enabled: true\n    collection: abc123\n"
    )

    result = await check_config_yaml()
    assert result.status == CheckStatus.OK
    assert "1 domínio" in result.message


@pytest.mark.asyncio
async def test_config_yaml_missing(tmp_path, monkeypatch):
    """Missing config.yaml returns FAIL."""
    monkeypatch.chdir(tmp_path)
    result = await check_config_yaml()
    assert result.status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_notion_token_skip(monkeypatch):
    """No NOTION_TOKEN returns SKIP."""
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    result = await check_notion_token()
    assert result.status == CheckStatus.SKIP


@pytest.mark.asyncio
async def test_notion_token_valid(monkeypatch):
    """Valid Notion token returns OK."""
    monkeypatch.setenv("NOTION_TOKEN", "ntnl_test")

    async def mock_validate(token):
        return True, "3 databases", []

    with patch("vera.setup.validators.validate_notion_token", mock_validate):
        result = await check_notion_token()

    assert result.status == CheckStatus.OK


@pytest.mark.asyncio
async def test_telegram_bot_skip(monkeypatch):
    """No Telegram token returns SKIP."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    result = await check_telegram_bot()
    assert result.status == CheckStatus.SKIP


@pytest.mark.asyncio
async def test_telegram_chat_id_ok(monkeypatch):
    """Chat ID set returns OK."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    result = await check_telegram_chat_id()
    assert result.status == CheckStatus.OK


@pytest.mark.asyncio
async def test_state_writable(tmp_path, monkeypatch):
    """State directory is writable."""
    monkeypatch.chdir(tmp_path)
    result = await check_state_writable()
    assert result.status == CheckStatus.OK


@pytest.mark.asyncio
async def test_user_md_missing(tmp_path, monkeypatch):
    """Missing USER.md returns WARN."""
    monkeypatch.chdir(tmp_path)
    result = await check_user_md()
    assert result.status == CheckStatus.WARN


@pytest.mark.asyncio
async def test_user_md_exists(tmp_path, monkeypatch):
    """Existing USER.md returns OK."""
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "USER.md").write_text("# User")
    result = await check_user_md()
    assert result.status == CheckStatus.OK


# ─── Aggregation ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_all_checks():
    """run_all_checks returns a list of CheckResults."""
    with patch("vera.doctor.ALL_CHECKS", [check_python_version]):
        results = await run_all_checks()
    assert len(results) == 1
    assert isinstance(results[0], CheckResult)


def test_print_results_no_failures(capsys):
    """Exit code 0 when no failures."""
    results = [
        CheckResult("Test1", CheckStatus.OK, "All good"),
        CheckResult("Test2", CheckStatus.WARN, "Minor issue"),
    ]
    exit_code = print_results(results)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "✓" in captured.out
    assert "⚠" in captured.out


def test_print_results_with_failure(capsys):
    """Exit code 1 when there are failures."""
    results = [
        CheckResult("Test1", CheckStatus.OK, "All good"),
        CheckResult("Test2", CheckStatus.FAIL, "Broken", fix_hint="Fix it"),
    ]
    exit_code = print_results(results)
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "✗" in captured.out
    assert "Fix it" in captured.out


def test_print_results_all_ok(capsys):
    """All checks passing shows success message."""
    results = [
        CheckResult("A", CheckStatus.OK, "ok"),
        CheckResult("B", CheckStatus.OK, "ok"),
    ]
    exit_code = print_results(results)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Tudo OK" in captured.out
