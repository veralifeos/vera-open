"""Tests for vera.setup.wizard — CliRunner with fallback mode (no InquirerPy)."""

from unittest.mock import AsyncMock, MagicMock, patch

import yaml
from typer.testing import CliRunner

from vera.cli import app

runner = CliRunner()


def _mock_httpx(post_resp=None, get_resp=None):
    """Create mock httpx.AsyncClient."""
    mock = AsyncMock()
    if post_resp:
        mock.post.return_value = post_resp
    if get_resp:
        mock.get.return_value = get_resp
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


def _resp(status_code=200, json_data=None):
    """Create a mock response."""
    r = MagicMock()
    r.status_code = status_code
    r.raise_for_status = MagicMock()
    r.json.return_value = json_data or {}
    r.text = ""
    r.request = MagicMock()
    return r


def _common_patches():
    """Common patches for all wizard tests."""
    return (
        patch("vera.setup.wizard.HAS_INQUIRER", False),
        patch("vera.doctor.run_all_checks", new_callable=AsyncMock, return_value=[]),
        patch("vera.doctor.print_results", return_value=0),
    )


def test_setup_wizard_minimal_preset(tmp_path, monkeypatch):
    """Setup with minimal preset generates valid config."""
    monkeypatch.chdir(tmp_path)

    inputs = "\n".join([
        "Vera",                     # nome
        "y",                        # timezone confirm
        "3",                        # objetivo: teste rápido (minimal)
        "",                         # notion token (empty = skip)
        "n",                        # telegram: não
        "2",                        # LLM: Ollama
        "http://localhost:11434",   # ollama url
        "llama3.2:3b",             # ollama model
        "1",                        # persona: executiva
    ])

    # Mock ollama /api/tags
    mock_client = _mock_httpx(
        get_resp=_resp(200, {"models": [{"name": "llama3.2:3b"}]})
    )

    p1, p2, p3 = _common_patches()
    with p1, p2, p3, \
         patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        result = runner.invoke(app, ["setup"], input=inputs)

    assert result.exit_code == 0, result.output
    assert "Setup completo" in result.output

    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert config["name"] == "Vera"
    assert "tasks" in config["domains"]
    assert config["llm"]["default"] == "ollama"


def test_setup_wizard_jobs_preset_with_notion(tmp_path, monkeypatch):
    """Setup with jobs preset + Notion token creates config with all domains."""
    monkeypatch.chdir(tmp_path)

    inputs = "\n".join([
        "Vera",                     # nome
        "y",                        # timezone confirm
        "1",                        # objetivo: recolocação (jobs)
        "ntnl_test_token",          # notion token
        "3",                        # db strategy: manual
        "n",                        # telegram: não
        "1",                        # LLM: Claude
        "sk-ant-test",              # API key
        "1",                        # persona: executiva
    ])

    # Mock: Notion search returns 200, Claude messages returns 200
    notion_resp = _resp(200, {
        "results": [{"id": "db1", "title": [{"plain_text": "Tasks"}]}]
    })
    claude_resp = _resp(200)

    # Need both post calls to succeed
    mock_client = AsyncMock()
    mock_client.post.return_value = notion_resp  # default
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Make post return different responses based on URL
    async def smart_post(url, **kwargs):
        if "notion" in url:
            return notion_resp
        return claude_resp

    mock_client.post = AsyncMock(side_effect=smart_post)

    p1, p2, p3 = _common_patches()
    with p1, p2, p3, \
         patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        result = runner.invoke(app, ["setup"], input=inputs)

    assert result.exit_code == 0, result.output

    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert config["backend"]["type"] == "notion"
    assert "tasks" in config["domains"]
    assert "pipeline" in config["domains"]
    assert config["llm"]["default"] == "claude"

    env_content = (tmp_path / ".env").read_text()
    assert "NOTION_TOKEN=ntnl_test_token" in env_content
    assert "ANTHROPIC_API_KEY=sk-ant-test" in env_content


def test_setup_wizard_config_has_schedule(tmp_path, monkeypatch):
    """Generated config includes schedule defaults."""
    monkeypatch.chdir(tmp_path)

    inputs = "\n".join([
        "Vera",
        "y",
        "3",                        # minimal
        "",                         # no notion token
        "n",                        # no telegram
        "2",                        # ollama
        "http://localhost:11434",
        "llama3.2:3b",
        "1",                        # executive
    ])

    mock_client = _mock_httpx(
        get_resp=_resp(200, {"models": []})
    )

    p1, p2, p3 = _common_patches()
    with p1, p2, p3, \
         patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        result = runner.invoke(app, ["setup"], input=inputs)

    assert result.exit_code == 0, result.output
    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert "schedule" in config
    assert config["schedule"]["briefing"] == "09:00"


def test_setup_detect_timezone():
    """Timezone detection returns valid IANA string."""
    from vera.setup.wizard import _detect_timezone

    tz = _detect_timezone()
    assert isinstance(tz, str)
    assert "/" in tz
