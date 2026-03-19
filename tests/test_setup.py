"""Testes do setup wizard (legado) — refatorado para novos module paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import yaml
from typer.testing import CliRunner

from vera.cli import app
from vera.setup.wizard import _detect_timezone

runner = CliRunner()


def test_detect_timezone():
    """Detecta timezone sem erro."""
    tz = _detect_timezone()
    assert isinstance(tz, str)
    assert "/" in tz  # formato IANA


def _mock_httpx_client(post_response=None, get_response=None):
    """Helper to mock httpx.AsyncClient for validators."""
    mock_client = AsyncMock()

    if post_response:
        mock_client.post.return_value = post_response
    if get_response:
        mock_client.get.return_value = get_response

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def test_setup_wizard_gera_config(tmp_path, monkeypatch):
    """Setup gera config.yaml válido com inputs simulados."""
    monkeypatch.chdir(tmp_path)

    with patch("vera.setup.wizard.HAS_INQUIRER", False):
        inputs = "\n".join(
            [
                "Vera",                     # nome
                "y",                        # timezone confirm
                "3",                        # objetivo: teste rápido
                "",                         # notion token (skip)
                "n",                        # Telegram: não
                "1",                        # LLM: Claude
                "sk-ant-test",              # API key
                "1",                        # Persona: executiva
            ]
        )

        # Mock httpx for Claude validation (returns 200 = valid)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client = _mock_httpx_client(post_response=mock_resp)

        with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client), \
             patch("vera.doctor.run_all_checks", new_callable=AsyncMock) as mc, \
             patch("vera.doctor.print_results", return_value=0):
            mc.return_value = []
            result = runner.invoke(app, ["setup"], input=inputs)

    assert result.exit_code == 0, result.output
    assert "Setup completo" in result.output

    config_path = tmp_path / "config.yaml"
    assert config_path.exists()

    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["name"] == "Vera"
    assert config["llm"]["default"] == "claude"
    assert "tasks" in config["domains"]

    env_path = tmp_path / ".env"
    assert env_path.exists()
    env_content = env_path.read_text()
    assert "ANTHROPIC_API_KEY=sk-ant-test" in env_content


def test_setup_wizard_ollama(tmp_path, monkeypatch):
    """Setup com Ollama não gera .env com API key."""
    monkeypatch.chdir(tmp_path)

    with patch("vera.setup.wizard.HAS_INQUIRER", False):
        inputs = "\n".join(
            [
                "Vera",
                "y",                        # timezone confirm
                "3",                        # minimal
                "",                         # no notion token
                "n",                        # no telegram
                "2",                        # LLM: Ollama
                "http://localhost:11434",
                "llama3.2:3b",
                "1",                        # persona
            ]
        )

        # Mock httpx for Ollama validation
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}
        mock_client = _mock_httpx_client(get_response=mock_resp)

        with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client), \
             patch("vera.doctor.run_all_checks", new_callable=AsyncMock) as mc, \
             patch("vera.doctor.print_results", return_value=0):
            mc.return_value = []
            result = runner.invoke(app, ["setup"], input=inputs)

    assert result.exit_code == 0, result.output

    config_path = tmp_path / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["llm"]["default"] == "ollama"

    env_path = tmp_path / ".env"
    if env_path.exists():
        assert "ANTHROPIC_API_KEY" not in env_path.read_text()
