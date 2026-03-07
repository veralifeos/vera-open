"""Testes da integracao Telegram."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.integrations.telegram import (
    _chunkar_mensagem,
    enviar_telegram,
    notificar_erro,
)

# ─── Chunking ─────────────────────────────────────────────────────────────────


def test_chunkar_mensagem_curta():
    """Mensagem curta nao e dividida."""
    chunks = _chunkar_mensagem("Oi")
    assert len(chunks) == 1
    assert chunks[0] == "Oi"


def test_chunkar_mensagem_longa():
    """Mensagem longa e dividida em chunks."""
    texto = "A" * 5000 + "\n" + "B" * 5000
    chunks = _chunkar_mensagem(texto)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 4096


def test_chunkar_mensagem_corta_na_quebra():
    """Chunks cortam na ultima quebra de linha."""
    lines = ["Linha " + str(i) for i in range(500)]
    texto = "\n".join(lines)
    chunks = _chunkar_mensagem(texto)
    assert len(chunks) >= 2
    # Cada chunk deve terminar em uma linha completa (exceto talvez o ultimo)
    for chunk in chunks[:-1]:
        assert chunk.endswith(str(chunk.split()[-1]))


# ─── Enviar Telegram ──────────────────────────────────────────────────────────


def test_enviar_telegram_sem_config():
    """Retorna False se nao configurado."""
    result = asyncio.run(enviar_telegram("teste", "", ""))
    assert result is False


def test_enviar_telegram_sucesso():
    """Envia com sucesso."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("vera.integrations.telegram.aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.run(enviar_telegram("teste", "tok123", "chat456"))

    assert result is True


def test_enviar_telegram_erro_levanta():
    """Erro no Telegram levanta excecao apos retry."""
    mock_resp = AsyncMock()
    mock_resp.status = 500
    mock_resp.text = AsyncMock(return_value="Internal Server Error")
    mock_resp.request_info = MagicMock()
    mock_resp.history = ()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    import aiohttp

    with patch("vera.integrations.telegram.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(aiohttp.ClientResponseError):
            asyncio.run(enviar_telegram("teste", "tok123", "chat456"))


# ─── Notificar Erro ───────────────────────────────────────────────────────────


def test_notificar_erro_nivel1_sucesso():
    """Nivel 1: enviar_telegram funciona."""
    with patch("vera.integrations.telegram.enviar_telegram", new_callable=AsyncMock) as mock_enviar:
        mock_enviar.return_value = True
        asyncio.run(notificar_erro("teste erro", "tok", "chat"))
        mock_enviar.assert_called_once()


def test_notificar_erro_nivel2_fallback():
    """Nivel 1 falha, nivel 2 (sync) funciona."""
    with patch(
        "vera.integrations.telegram.enviar_telegram",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        with patch("vera.integrations.telegram._enviar_sync_fallback") as mock_sync:
            asyncio.run(notificar_erro("teste erro", "tok", "chat"))
            mock_sync.assert_called_once()


def test_notificar_erro_nivel3_stderr(capsys):
    """Tudo falha, vai para stderr."""
    with patch(
        "vera.integrations.telegram.enviar_telegram",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        with patch(
            "vera.integrations.telegram._enviar_sync_fallback", side_effect=Exception("fail2")
        ):
            asyncio.run(notificar_erro("teste erro", "tok", "chat"))

    captured = capsys.readouterr()
    assert "VERA ERRO" in captured.err
    assert "teste erro" in captured.err


def test_notificar_erro_mensagem_formatada():
    """Mensagem contem tipo de erro e timestamp."""
    mensagens_enviadas = []

    async def capture_msg(msg, tok, chat):
        mensagens_enviadas.append(msg)
        return True

    with patch("vera.integrations.telegram.enviar_telegram", side_effect=capture_msg):
        asyncio.run(notificar_erro("TypeError: bad value", "tok", "chat"))

    assert len(mensagens_enviadas) == 1
    assert "TypeError: bad value" in mensagens_enviadas[0]
    assert "Timestamp:" in mensagens_enviadas[0]
