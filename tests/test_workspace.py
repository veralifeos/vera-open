"""Testes de workspace files e persona presets."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vera.modes.briefing import _get_system_prompt, carregar_workspace_files
from vera.personas import PRESETS, get_persona_prompt


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _minimal_config(**overrides):
    from vera.config import VeraConfig

    data = {
        "name": "Vera",
        "timezone": "America/Sao_Paulo",
        "backend": {"type": "notion", "notion": {"token_env": "NOTION_TOKEN"}},
        "llm": {
            "default": "claude",
            "providers": {"claude": {"model": "test", "api_key_env": "KEY"}},
        },
        "domains": {
            "tasks": {
                "enabled": True,
                "collection": "db123",
                "fields": {
                    "title": "Name",
                    "status": "Status",
                    "priority": "Prioridade",
                    "deadline": "Deadline",
                    "status_active": ["To Do", "Doing"],
                },
            }
        },
        "schedule": {"briefing": "09:00"},
        "persona": {"preset": "executive"},
    }
    data.update(overrides)
    return VeraConfig(**data)


# ─── Workspace files ─────────────────────────────────────────────────────────


def test_carregar_agent_md(tmp_path, monkeypatch):
    """Carrega AGENT.md quando existe."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENT.md").write_text("Persona custom", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = _minimal_config()
    files = carregar_workspace_files(config)
    assert "AGENT.md" in files
    assert "Persona custom" in files["AGENT.md"]


def test_carregar_user_md(tmp_path, monkeypatch):
    """Carrega USER.md quando existe."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "USER.md").write_text("Perfil do usuario", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = _minimal_config()
    files = carregar_workspace_files(config)
    assert "USER.md" in files
    assert "Perfil do usuario" in files["USER.md"]


def test_nenhum_arquivo_retorna_vazio(tmp_path, monkeypatch):
    """Sem workspace files retorna dict vazio."""
    monkeypatch.chdir(tmp_path)
    config = _minimal_config()
    files = carregar_workspace_files(config)
    assert files == {}


def test_example_como_fallback(tmp_path, monkeypatch):
    """Usa .example.md como fallback."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENT.example.md").write_text("Persona example", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = _minimal_config()
    files = carregar_workspace_files(config)
    assert "AGENT.md" in files
    assert "Persona example" in files["AGENT.md"]


# ─── Persona presets ──────────────────────────────────────────────────────────


def test_preset_executive():
    """Preset executive gera prompt com nome e max_words."""
    prompt = get_persona_prompt("executive", "Vera", 400)
    assert "Vera" in prompt
    assert "400" in prompt
    assert "secretaria executiva" in prompt.lower()


def test_preset_coach():
    """Preset coach gera prompt com nome."""
    prompt = get_persona_prompt("coach", "Ana", 350)
    assert "Ana" in prompt
    assert "350" in prompt
    assert "coach" in prompt.lower()


def test_preset_desconhecido_usa_executive():
    """Preset desconhecido fallback para executive."""
    prompt = get_persona_prompt("unknown", "Bot", 300)
    assert "secretaria executiva" in prompt.lower()


def test_custom_sobrescreve_preset():
    """Se AGENT.md existe e preset e 'custom', usa AGENT.md."""
    config = _minimal_config(persona={"preset": "custom"})
    workspace = {"AGENT.md": "Eu sou uma persona totalmente customizada."}
    prompt = _get_system_prompt(config, workspace)
    assert "persona totalmente customizada" in prompt


def test_user_md_injetado_no_prompt():
    """USER.md e injetado no system prompt."""
    config = _minimal_config()
    workspace = {"USER.md": "Fernando, 32 anos, engenheiro"}
    prompt = _get_system_prompt(config, workspace)
    assert "SOBRE O USUARIO" in prompt
    assert "Fernando" in prompt
