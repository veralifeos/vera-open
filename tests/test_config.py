"""Testes do sistema de configuração."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from vera.config import VeraConfig, check_required_secrets, load_config

# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_config_file(tmp_path: Path, data: dict) -> Path:
    """Cria um config.yaml temporário."""
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return config_path


def _minimal_config() -> dict:
    """Config mínimo válido."""
    return {
        "name": "Vera",
        "timezone": "America/Sao_Paulo",
        "backend": {"type": "notion", "notion": {"token_env": "NOTION_TOKEN"}},
        "llm": {
            "default": "claude",
            "providers": {
                "claude": {
                    "model": "claude-sonnet-4-5-20250929",
                    "api_key_env": "ANTHROPIC_API_KEY",
                }
            },
        },
        "domains": {
            "tasks": {
                "enabled": True,
                "collection": "abc123",
                "fields": {
                    "title": "Name",
                    "status": "Status",
                    "priority": "Prioridade",
                    "deadline": "Deadline",
                },
            }
        },
    }


# ─── Testes de carregamento ──────────────────────────────────────────────────


def test_load_config_valido(tmp_path):
    """Carrega config YAML válido."""
    config_path = _make_config_file(tmp_path, _minimal_config())
    config = load_config(config_path)
    assert config.name == "Vera"
    assert config.timezone == "America/Sao_Paulo"
    assert config.backend.type == "notion"


def test_load_config_arquivo_nao_encontrado():
    """Erro claro se config.yaml não existe."""
    with pytest.raises(FileNotFoundError, match="config.yaml"):
        load_config("/tmp/nao_existe_vera_test.yaml")


def test_load_config_com_env_var(tmp_path):
    """Fallback para VERA_CONFIG env var."""
    config_path = _make_config_file(tmp_path, _minimal_config())
    with patch.dict(os.environ, {"VERA_CONFIG": str(config_path)}):
        config = load_config()
        assert config.name == "Vera"


def test_config_tasks_obrigatorio():
    """Tasks é auto-adicionado se não presente."""
    config = VeraConfig()
    assert "tasks" in config.domains
    assert config.domains["tasks"].enabled is True


def test_config_valores_default():
    """Valores default são preenchidos corretamente."""
    config = VeraConfig()
    assert config.name == "Vera"
    assert config.language == "pt-BR"
    assert config.timezone == "America/Sao_Paulo"
    assert config.debug.dry_run is False


def test_config_dominios_opcionais(tmp_path):
    """Domínios opcionais podem ser habilitados."""
    data = _minimal_config()
    data["domains"]["pipeline"] = {"enabled": True, "collection": "xyz789"}
    config_path = _make_config_file(tmp_path, data)
    config = load_config(config_path)
    assert config.domains["pipeline"].enabled is True
    assert config.domains["pipeline"].collection == "xyz789"


# ─── Testes de validação de secrets ──────────────────────────────────────────


def test_check_secrets_ok():
    """Sem erros quando env vars estão definidas."""
    config = VeraConfig(**_minimal_config())
    with patch.dict(os.environ, {"NOTION_TOKEN": "token", "ANTHROPIC_API_KEY": "key"}):
        errors = check_required_secrets(config)
        assert errors == []


def test_check_secrets_notion_faltando():
    """Erro se NOTION_TOKEN não definida."""
    config = VeraConfig(**_minimal_config())
    with patch.dict(os.environ, {}, clear=True):
        errors = check_required_secrets(config)
        assert any("NOTION_TOKEN" in e for e in errors)


def test_check_secrets_llm_faltando():
    """Erro se API key do LLM não definida."""
    config = VeraConfig(**_minimal_config())
    with patch.dict(os.environ, {"NOTION_TOKEN": "token"}, clear=True):
        errors = check_required_secrets(config)
        assert any("ANTHROPIC_API_KEY" in e for e in errors)


def test_config_ollama_sem_api_key():
    """Ollama não precisa de api_key_env."""
    data = _minimal_config()
    data["llm"] = {
        "default": "ollama",
        "providers": {"ollama": {"model": "llama3.2:3b", "base_url": "http://localhost:11434"}},
    }
    config = VeraConfig(**data)
    with patch.dict(os.environ, {"NOTION_TOKEN": "token"}, clear=True):
        errors = check_required_secrets(config)
        # Não deve ter erro de API key para ollama
        assert not any("api_key" in e.lower() for e in errors)


def test_config_fields_customizaveis(tmp_path):
    """Nomes de campos podem ser customizados."""
    data = _minimal_config()
    data["domains"]["tasks"]["fields"] = {
        "title": "Título",
        "status": "Estado",
        "priority": "Importância",
        "deadline": "Prazo",
        "status_active": ["Aberto", "Fazendo"],
    }
    config_path = _make_config_file(tmp_path, data)
    config = load_config(config_path)
    fields = config.domains["tasks"].fields
    assert fields["title"] == "Título"
    assert fields["status_active"] == ["Aberto", "Fazendo"]
