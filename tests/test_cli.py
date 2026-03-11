"""Testes da CLI."""

from unittest.mock import patch

from typer.testing import CliRunner

from vera.cli import app

runner = CliRunner()


def test_cli_help():
    """--help funciona e mostra subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "briefing" in result.output
    assert "validate" in result.output
    assert "setup" in result.output


def test_cli_version():
    """--version mostra versão."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.output


def test_cli_briefing_help():
    """briefing --help funciona."""
    result = runner.invoke(app, ["briefing", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output
    assert "--dry-run" in result.output


def test_cli_validate_help():
    """validate --help funciona."""
    result = runner.invoke(app, ["validate", "--help"])
    assert result.exit_code == 0


def test_cli_setup_help():
    """setup --help funciona."""
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0


def test_cli_no_args_shows_help():
    """Sem argumentos mostra help."""
    result = runner.invoke(app, [])
    # Typer retorna exit_code 0 com no_args_is_help
    assert "briefing" in result.output


def test_cli_briefing_weekly_help():
    """briefing --help mostra flag --weekly."""
    result = runner.invoke(app, ["briefing", "--help"])
    assert result.exit_code == 0
    assert "--weekly" in result.output


def test_cli_research_all_help():
    """research --help mostra flag --all."""
    result = runner.invoke(app, ["research", "--help"])
    assert result.exit_code == 0
    assert "--all" in result.output


def test_cli_briefing_sem_config(tmp_path, monkeypatch):
    """Briefing sem config.yaml retorna erro."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VERA_CONFIG", raising=False)
    result = runner.invoke(app, ["briefing"])
    assert result.exit_code == 1
    assert "erro" in result.output.lower()
