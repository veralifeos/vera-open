"""Testes de retry com backoff exponencial."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

# ─── Notion retry ─────────────────────────────────────────────────────────────


def test_notion_retry_sucesso_na_terceira():
    """NotionBackend._request retenta e sucede na 3a tentativa."""
    from vera.backends.notion import NotionBackend

    backend = NotionBackend(token="test_token")
    call_count = 0

    def mock_request(method, url, json=None, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # Retorna context manager que levanta erro no __aenter__
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection reset"))
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"results": [{"id": "r1"}], "has_more": False})
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    mock_session = MagicMock()
    mock_session.request = MagicMock(side_effect=mock_request)

    result = asyncio.run(backend._request(mock_session, "POST", "http://test", {"page_size": 100}))
    assert result["results"][0]["id"] == "r1"
    assert call_count == 3


def test_notion_retry_todas_falham():
    """NotionBackend falha apos 3 tentativas."""
    from vera.backends.notion import NotionBackend

    backend = NotionBackend(token="test_token")

    def mock_request(*args, **kwargs):
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Server down"))
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    mock_session = MagicMock()
    mock_session.request = MagicMock(side_effect=mock_request)

    with pytest.raises(aiohttp.ClientError, match="Server down"):
        asyncio.run(backend._request(mock_session, "POST", "http://test", {}))


# ─── Claude retry ─────────────────────────────────────────────────────────────


def test_claude_retry_sucesso_na_segunda():
    """ClaudeProvider retenta e sucede na 2a tentativa."""
    from anthropic import APIConnectionError

    call_count = 0

    class MockClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise APIConnectionError(request=MagicMock())
                mock_msg = MagicMock()
                mock_msg.content = [MagicMock(text="Resposta OK")]
                return mock_msg

    with patch("vera.llm.claude.Anthropic", return_value=MockClient()):
        from vera.llm.claude import ClaudeProvider

        provider = ClaudeProvider(model="test", api_key="sk-test")
        provider._client = MockClient()

        result = asyncio.run(provider.generate("sys", "user"))

    assert result == "Resposta OK"
    assert call_count == 2


# ─── Ollama retry ─────────────────────────────────────────────────────────────


def test_ollama_retry_timeout():
    """OllamaProvider retenta apos timeout."""
    from vera.llm.ollama import OllamaProvider

    provider = OllamaProvider(model="test", base_url="http://localhost:11434")
    call_count = 0

    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Connection timeout"))
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"message": {"content": "OK"}})
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=mock_post)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.llm.ollama.aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.run(provider.generate("sys", "user"))

    assert result == "OK"
    assert call_count == 2


# ─── Telegram retry ──────────────────────────────────────────────────────────


def test_telegram_retry_sucesso():
    """Telegram retenta apos falha."""
    call_count = 0

    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("Server Error"))
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm
        mock_resp = AsyncMock()
        mock_resp.status = 200
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=mock_post)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    from vera.integrations.telegram import enviar_telegram

    with patch("vera.integrations.telegram.aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.run(enviar_telegram("teste", "tok", "chat"))

    assert result is True
    assert call_count == 2
