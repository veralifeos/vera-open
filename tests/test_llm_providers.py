"""Testes dos LLM providers."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.llm.base import LLMProvider
from vera.llm.claude import ClaudeProvider
from vera.llm.ollama import OllamaProvider


# ─── Testes da interface ─────────────────────────────────────────────────────


def test_llm_provider_e_abstrato():
    """LLMProvider não pode ser instanciado diretamente."""
    with pytest.raises(TypeError):
        LLMProvider()


def test_llm_provider_metodos_obrigatorios():
    """Verifica que todos os métodos abstratos estão definidos."""
    abstract_methods = LLMProvider.__abstractmethods__
    expected = {"generate", "generate_structured"}
    assert expected == abstract_methods


# ─── ClaudeProvider ──────────────────────────────────────────────────────────


def test_claude_provider_implementa_interface():
    """ClaudeProvider é subclasse de LLMProvider."""
    assert issubclass(ClaudeProvider, LLMProvider)


def test_claude_provider_sem_key_raises():
    """Erro se API key não fornecida."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="API key"):
            ClaudeProvider(api_key_env="ANTHROPIC_KEY_INEXISTENTE")


def test_claude_provider_com_key():
    """Cria instância com API key direta."""
    provider = ClaudeProvider(api_key="sk-ant-test")
    assert provider._model == "claude-sonnet-4-5-20250929"


def test_claude_provider_model_customizado():
    """Aceita model customizado."""
    provider = ClaudeProvider(api_key="sk-ant-test", model="claude-haiku-4-5-20251001")
    assert provider._model == "claude-haiku-4-5-20251001"


def test_claude_generate(monkeypatch):
    """Generate chama API e retorna texto."""
    provider = ClaudeProvider(api_key="sk-ant-test")

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="  Olá mundo  ")]

    mock_create = MagicMock(return_value=mock_message)
    monkeypatch.setattr(provider._client.messages, "create", mock_create)

    result = asyncio.run(provider.generate("system", "user"))
    assert result == "Olá mundo"
    mock_create.assert_called_once()


def test_claude_generate_structured(monkeypatch):
    """generate_structured retorna dict parseado."""
    provider = ClaudeProvider(api_key="sk-ant-test")

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 8.5, "reason": "bom"}')]

    mock_create = MagicMock(return_value=mock_message)
    monkeypatch.setattr(provider._client.messages, "create", mock_create)

    result = asyncio.run(
        provider.generate_structured(
            "system", "user", schema={"score": "number", "reason": "string"}
        )
    )
    assert result["score"] == 8.5
    assert result["reason"] == "bom"


def test_claude_generate_structured_code_block(monkeypatch):
    """Parseia JSON mesmo dentro de code block."""
    provider = ClaudeProvider(api_key="sk-ant-test")

    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(text='```json\n{"value": 42}\n```')
    ]

    mock_create = MagicMock(return_value=mock_message)
    monkeypatch.setattr(provider._client.messages, "create", mock_create)

    result = asyncio.run(
        provider.generate_structured("system", "user", schema={"value": "number"})
    )
    assert result["value"] == 42


# ─── OllamaProvider ─────────────────────────────────────────────────────────


def test_ollama_provider_implementa_interface():
    """OllamaProvider é subclasse de LLMProvider."""
    assert issubclass(OllamaProvider, LLMProvider)


def test_ollama_provider_defaults():
    """Valores default corretos."""
    provider = OllamaProvider()
    assert provider._model == "llama3.2:3b"
    assert provider._base_url == "http://localhost:11434"


def test_ollama_provider_customizado():
    """Aceita model e base_url customizados."""
    provider = OllamaProvider(model="mistral:7b", base_url="http://gpu:11434")
    assert provider._model == "mistral:7b"
    assert provider._base_url == "http://gpu:11434"


def test_ollama_generate():
    """Generate chama API Ollama e retorna texto."""
    provider = OllamaProvider()

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={"message": {"content": "  Resposta do Ollama  "}}
    )

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_resp),
        __aexit__=AsyncMock(return_value=False),
    ))

    with patch("aiohttp.ClientSession", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_session),
        __aexit__=AsyncMock(return_value=False),
    )):
        result = asyncio.run(provider.generate("system", "user"))
        assert result == "Resposta do Ollama"


def test_ollama_generate_structured():
    """generate_structured retorna dict parseado."""
    provider = OllamaProvider()

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={"message": {"content": '{"score": 7}'}}
    )

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_resp),
        __aexit__=AsyncMock(return_value=False),
    ))

    with patch("aiohttp.ClientSession", return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_session),
        __aexit__=AsyncMock(return_value=False),
    )):
        result = asyncio.run(
            provider.generate_structured("system", "user", schema={"score": "number"})
        )
        assert result["score"] == 7
