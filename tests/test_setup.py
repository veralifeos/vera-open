"""Testes do setup wizard."""

from unittest.mock import AsyncMock, patch

import yaml
from typer.testing import CliRunner

from vera.cli import _detect_timezone, _try_notion_discovery, app

runner = CliRunner()


def test_detect_timezone():
    """Detecta timezone sem erro."""
    tz = _detect_timezone()
    assert isinstance(tz, str)
    assert "/" in tz  # formato IANA


def test_notion_discovery_sem_token(monkeypatch):
    """Auto-discovery retorna lista vazia sem token válido."""
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    result = _try_notion_discovery("")
    assert result == []


def test_notion_discovery_com_erro():
    """Auto-discovery retorna lista vazia em caso de erro."""
    with patch("vera.backends.notion.NotionBackend") as MockBackend:
        MockBackend.side_effect = Exception("Falha")
        result = _try_notion_discovery("ntnl_fake")
        assert result == []


def test_notion_discovery_com_resultados():
    """Auto-discovery retorna databases encontrados."""
    mock_backend = AsyncMock()
    mock_backend.search_databases = AsyncMock(
        return_value=[
            {"id": "db1", "title": "Vera — Tasks"},
            {"id": "db2", "title": "Vera — Pipeline"},
        ]
    )

    with patch("vera.backends.notion.NotionBackend", return_value=mock_backend):
        result = _try_notion_discovery("ntnl_fake")
        assert len(result) == 2
        assert result[0]["title"] == "Vera — Tasks"


def test_setup_wizard_gera_config(tmp_path, monkeypatch):
    """Setup gera config.yaml válido com inputs simulados."""
    monkeypatch.chdir(tmp_path)

    # Simula inputs do usuário
    inputs = "\n".join(
        [
            "Vera",  # nome
            "pt-BR",  # idioma
            "America/Sao_Paulo",  # timezone
            "2",  # backend: Outro
            "1",  # LLM: Claude
            "sk-ant-test",  # API key
            "n",  # Telegram: não
            "1",  # Persona: executiva
            "",  # Tasks collection ID
            "n",  # Pipeline: não
            "n",  # Contacts: não
            "n",  # Health: não
            "n",  # Finances: não
            "n",  # Learning: não
        ]
    )

    result = runner.invoke(app, ["setup"], input=inputs)
    assert result.exit_code == 0
    assert "Setup completo" in result.output

    # Verifica config.yaml gerado
    config_path = tmp_path / "config.yaml"
    assert config_path.exists()

    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["name"] == "Vera"
    assert config["timezone"] == "America/Sao_Paulo"
    assert config["llm"]["default"] == "claude"
    assert "tasks" in config["domains"]

    # Verifica .env gerado
    env_path = tmp_path / ".env"
    assert env_path.exists()
    env_content = env_path.read_text()
    assert "ANTHROPIC_API_KEY=sk-ant-test" in env_content


def test_setup_wizard_notion_auto_discovery(tmp_path, monkeypatch):
    """Setup com Notion faz auto-discovery."""
    monkeypatch.chdir(tmp_path)

    mock_backend = AsyncMock()
    mock_backend.search_databases = AsyncMock(
        return_value=[
            {"id": "task_db_id", "title": "Vera — Tasks"},
        ]
    )

    with patch("vera.backends.notion.NotionBackend", return_value=mock_backend):
        inputs = "\n".join(
            [
                "Vera",  # nome
                "pt-BR",  # idioma
                "America/Sao_Paulo",  # timezone
                "1",  # backend: Notion
                "ntnl_test",  # token
                "2",  # LLM: Ollama
                "llama3.2:3b",  # model
                "http://localhost:11434",  # url
                "n",  # Telegram
                "1",  # Persona
                # tasks collection auto-detectado, não pede
                "n",  # Pipeline
                "n",  # Contacts
                "n",  # Health
                "n",  # Finances
                "n",  # Learning
            ]
        )

        result = runner.invoke(app, ["setup"], input=inputs)
        assert result.exit_code == 0

        config_path = tmp_path / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config["backend"]["type"] == "notion"
        assert config["domains"]["tasks"]["collection"] == "task_db_id"


def test_setup_wizard_ollama(tmp_path, monkeypatch):
    """Setup com Ollama não gera .env com API key."""
    monkeypatch.chdir(tmp_path)

    inputs = "\n".join(
        [
            "Vera",
            "pt-BR",
            "America/Sao_Paulo",
            "2",  # backend: Outro
            "2",  # LLM: Ollama
            "llama3.2:3b",
            "http://localhost:11434",
            "n",  # Telegram
            "1",  # Persona
            "",  # Tasks collection
            "n",
            "n",
            "n",
            "n",
            "n",  # Domínios opcionais
        ]
    )

    result = runner.invoke(app, ["setup"], input=inputs)
    assert result.exit_code == 0

    config_path = tmp_path / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["llm"]["default"] == "ollama"

    # Sem API key, .env não deveria ter ANTHROPIC_API_KEY
    env_path = tmp_path / ".env"
    if env_path.exists():
        assert "ANTHROPIC_API_KEY" not in env_path.read_text()
