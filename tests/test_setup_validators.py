"""Tests for vera.setup.validators — each validator mocked."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.setup.validators import (
    detect_telegram_chat_id,
    validate_claude_api_key,
    validate_notion_token,
    validate_ollama_connection,
    validate_telegram_token,
)


# ─── Notion Token ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notion_token_valid():
    """Valid token returns success + databases."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"id": "db1", "title": [{"plain_text": "Tasks"}]},
            {"id": "db2", "title": [{"plain_text": "Pipeline"}]},
        ]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg, dbs = await validate_notion_token("ntnl_test")

    assert ok is True
    assert len(dbs) == 2
    assert dbs[0]["title"] == "Tasks"


@pytest.mark.asyncio
async def test_notion_token_invalid():
    """Invalid token returns 401."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg, dbs = await validate_notion_token("bad_token")

    assert ok is False
    assert "inválido" in msg


@pytest.mark.asyncio
async def test_notion_token_network_error():
    """Network error returns failure."""
    import httpx

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg, dbs = await validate_notion_token("ntnl_test")

    assert ok is False
    assert "conexão" in msg.lower()


# ─── Telegram Token ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_telegram_token_valid():
    """Valid bot token returns success + username."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": {"username": "vera_bot"},
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg, username = await validate_telegram_token("123:ABC")

    assert ok is True
    assert username == "vera_bot"


@pytest.mark.asyncio
async def test_telegram_token_invalid():
    """Invalid token returns failure."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": False,
        "description": "Unauthorized",
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg, username = await validate_telegram_token("bad")

    assert ok is False
    assert username == ""


# ─── Telegram Chat ID Detection ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_chat_id_success():
    """Detects chat_id from getUpdates."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ok": True,
        "result": [
            {"message": {"chat": {"id": 12345}}}
        ],
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg, chat_id = await detect_telegram_chat_id("123:ABC", timeout=1)

    assert ok is True
    assert chat_id == "12345"


@pytest.mark.asyncio
async def test_detect_chat_id_no_messages():
    """No messages returns failure."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "result": []}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg, chat_id = await detect_telegram_chat_id("123:ABC", timeout=1)

    assert ok is False


# ─── Claude API Key ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claude_key_valid():
    """Valid API key returns success."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg = await validate_claude_api_key("sk-ant-test")

    assert ok is True


@pytest.mark.asyncio
async def test_claude_key_invalid():
    """Invalid API key returns 401."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg = await validate_claude_api_key("bad-key")

    assert ok is False
    assert "inválida" in msg


@pytest.mark.asyncio
async def test_claude_key_rate_limited_is_valid():
    """Rate-limited (429) means key is valid."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg = await validate_claude_api_key("sk-ant-test")

    assert ok is True


# ─── Ollama ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ollama_connected():
    """Ollama running returns success."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "llama3.2:3b"}, {"name": "codellama:7b"}]
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg = await validate_ollama_connection()

    assert ok is True
    assert "llama3.2:3b" in msg


@pytest.mark.asyncio
async def test_ollama_not_running():
    """Ollama not running returns failure."""
    import httpx

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg = await validate_ollama_connection()

    assert ok is False
    assert "não encontrado" in msg.lower()


@pytest.mark.asyncio
async def test_ollama_no_models():
    """Ollama running but no models installed."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": []}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.setup.validators.httpx.AsyncClient", return_value=mock_client):
        ok, msg = await validate_ollama_connection()

    assert ok is True
    assert "nenhum modelo" in msg.lower()
