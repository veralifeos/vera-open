"""Telegram integration — envio de mensagens com chunking e fallback de 3 niveis."""

import os
import ssl
import sys
from datetime import datetime, timezone

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
MAX_MESSAGE_LENGTH = 4096

_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=2, min=2, max=30),
    "retry": retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
    "reraise": True,
}


def _chunkar_mensagem(texto: str, max_len: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Divide mensagem em chunks respeitando limite do Telegram."""
    if len(texto) <= max_len:
        return [texto]

    chunks = []
    while texto:
        if len(texto) <= max_len:
            chunks.append(texto)
            break
        # Tenta cortar na última quebra de linha antes do limite
        corte = texto[:max_len].rfind("\n")
        if corte < max_len // 2:
            corte = max_len
        chunks.append(texto[:corte])
        texto = texto[corte:].lstrip("\n")

    return chunks


@retry(**_RETRY_KWARGS)
async def enviar_telegram(mensagem: str, bot_token: str, chat_id: str) -> bool:
    """Envia mensagem no Telegram com chunking e retry.

    Returns:
        True se enviou com sucesso, False caso contrário.
    """
    if not bot_token or not chat_id:
        print("   [telegram] Nao configurado — pulando envio.")
        return False

    base_url = TELEGRAM_API.format(token=bot_token)
    chunks = _chunkar_mensagem(mensagem)

    # SSL: desabilita verificação se VERA_SSL_VERIFY=0 (proxy/antivírus local)
    ssl_context: ssl.SSLContext | bool | None = None
    if os.environ.get("VERA_SSL_VERIFY", "1") == "0":
        ssl_context = False

    connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context is False else None
    async with aiohttp.ClientSession(connector=connector) as session:
        for i, chunk in enumerate(chunks):
            url = f"{base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
            }
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.post(url, json=payload, timeout=timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=f"Telegram erro {resp.status}: {text[:200]}",
                    )
            if i < len(chunks) - 1:
                import asyncio

                await asyncio.sleep(0.3)

    print(f"   [telegram] Enviado ({len(chunks)} parte(s))")
    return True


async def notificar_erro(error: str, bot_token: str, chat_id: str) -> None:
    """Notifica erro via Telegram com fallback de 3 niveis.

    Nivel 1: enviar_telegram() normal (async com retry)
    Nivel 2: requests.post direto na API (sync, sem dependencia da lib)
    Nivel 3: print no stderr (capturado pelo GitHub Actions)
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mensagem = (
        "Vera [briefing] falhou\n\n"
        f"Erro: {error[:300]}\n"
        f"Timestamp: {timestamp}\n\n"
        "Verifique os logs do GitHub Actions."
    )

    # Nivel 1: enviar_telegram async
    try:
        await enviar_telegram(mensagem, bot_token, chat_id)
        return
    except Exception:
        pass

    # Nivel 2: requests sync direto
    try:
        _enviar_sync_fallback(mensagem, bot_token, chat_id)
        return
    except Exception:
        pass

    # Nivel 3: stderr
    print(f"[VERA ERRO] {mensagem}", file=sys.stderr)


def _enviar_sync_fallback(mensagem: str, bot_token: str, chat_id: str) -> None:
    """Fallback sync usando urllib (sem dependencia de aiohttp)."""
    import json
    import urllib.request

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = json.dumps(
        {
            "chat_id": chat_id,
            "text": mensagem[:MAX_MESSAGE_LENGTH],
            "parse_mode": "Markdown",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)
