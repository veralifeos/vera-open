"""Inline validators for setup wizard — all async, all use httpx."""

import os

import httpx

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"
TELEGRAM_API = "https://api.telegram.org"
CLAUDE_API = "https://api.anthropic.com/v1"


def _ssl_verify() -> bool:
    """Respect VERA_SSL_VERIFY=0 for proxy/antivirus environments."""
    return os.environ.get("VERA_SSL_VERIFY", "1") != "0"


async def validate_notion_token(token: str) -> tuple[bool, str, list[dict]]:
    """Validate Notion integration token via POST /v1/search.

    Returns: (success, message, discovered_databases)
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }
    payload = {
        "filter": {"value": "database", "property": "object"},
        "page_size": 100,
    }

    try:
        async with httpx.AsyncClient(verify=_ssl_verify(), timeout=15) as client:
            resp = await client.post(
                f"{NOTION_BASE_URL}/search", headers=headers, json=payload
            )

            if resp.status_code == 401:
                return False, "Token inválido ou revogado.", []
            if resp.status_code == 403:
                return False, "Token sem permissão. Verifique a integração.", []
            resp.raise_for_status()

            data = resp.json()
            databases = []
            for db in data.get("results", []):
                title_parts = db.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_parts)
                databases.append({"id": db["id"], "title": title})

            return True, f"{len(databases)} database(s) acessível(is).", databases

    except httpx.ConnectError:
        return False, "Erro de conexão. Verifique sua internet.", []
    except httpx.HTTPStatusError as e:
        return False, f"Erro HTTP {e.response.status_code}.", []
    except Exception as e:
        return False, f"Erro: {e}", []


async def validate_telegram_token(token: str) -> tuple[bool, str, str]:
    """Validate Telegram bot token via GET /bot{token}/getMe.

    Returns: (success, message, bot_username)
    """
    try:
        async with httpx.AsyncClient(verify=_ssl_verify(), timeout=10) as client:
            resp = await client.get(f"{TELEGRAM_API}/bot{token}/getMe")
            data = resp.json()

            if data.get("ok"):
                username = data["result"].get("username", "")
                return True, f"Bot @{username} conectado.", username
            else:
                desc = data.get("description", "Token inválido")
                return False, f"Telegram: {desc}", ""

    except httpx.ConnectError:
        return False, "Erro de conexão com Telegram API.", ""
    except Exception as e:
        return False, f"Erro: {e}", ""


async def detect_telegram_chat_id(token: str, timeout: float = 30) -> tuple[bool, str, str]:
    """Wait for a message to the bot and extract chat_id via getUpdates.

    Returns: (success, message, chat_id)
    """
    try:
        async with httpx.AsyncClient(verify=_ssl_verify(), timeout=timeout + 5) as client:
            resp = await client.get(
                f"{TELEGRAM_API}/bot{token}/getUpdates",
                params={"timeout": int(timeout), "limit": 1},
            )
            data = resp.json()

            if data.get("ok") and data.get("result"):
                update = data["result"][-1]
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id:
                    return True, f"Chat ID detectado: {chat_id}", chat_id

            return False, "Nenhuma mensagem recebida. Mande /start pro bot.", ""

    except httpx.ReadTimeout:
        return False, "Timeout — nenhuma mensagem recebida.", ""
    except Exception as e:
        return False, f"Erro: {e}", ""


async def validate_claude_api_key(key: str) -> tuple[bool, str]:
    """Validate Anthropic API key via POST /v1/messages with minimal request.

    Returns: (success, message)
    """
    headers = {
        "x-api-key": key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "ok"}],
    }

    try:
        async with httpx.AsyncClient(verify=_ssl_verify(), timeout=15) as client:
            resp = await client.post(
                f"{CLAUDE_API}/messages", headers=headers, json=payload
            )

            if resp.status_code == 401:
                return False, "API key inválida."
            if resp.status_code == 403:
                return False, "API key sem permissão ou conta suspensa."
            if resp.status_code in (200, 429):
                # 429 = rate limited but key is valid
                return True, "API key válida."
            resp.raise_for_status()
            return True, "API key válida."

    except httpx.ConnectError:
        return False, "Erro de conexão com Anthropic API."
    except Exception as e:
        return False, f"Erro: {e}"


async def validate_ollama_connection(url: str = "http://localhost:11434") -> tuple[bool, str]:
    """Check Ollama is running via GET /api/tags.

    Returns: (success, message)
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "?") for m in data.get("models", [])]
                if models:
                    return True, f"Ollama OK. Modelos: {', '.join(models[:5])}"
                return True, "Ollama conectado (nenhum modelo instalado)."
            return False, f"Ollama respondeu com status {resp.status_code}."

    except httpx.ConnectError:
        return False, f"Ollama não encontrado em {url}. Está rodando?"
    except Exception as e:
        return False, f"Erro: {e}"
