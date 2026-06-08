"""Env vars para modulos pessoais (bot + astro).

Lidos do ambiente, mesmo padrao do vera-private. Nao interferir com
vera.config — este arquivo e escopo do pacote personal/.
"""

import os
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")


def _e(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# Notion
NOTION_TOKEN = _e("NOTION_TOKEN")
NOTION_DB_ACOES = _e("NOTION_DB_ACOES")
NOTION_DB_LINHA_CEU = _e("NOTION_DB_LINHA_CEU")
NOTION_DB_CHECK = _e("NOTION_DB_CHECK")
NOTION_DB_PIPELINE = _e("NOTION_DB_PIPELINE")

# Pagina Notion com o mapa natal estruturado (Mapa Natal Fernando Fidelis)
NOTION_PAGE_NATAL = _e("NOTION_PAGE_NATAL")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# Anthropic / Telegram
ANTHROPIC_API_KEY = _e("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = _e("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _e("TELEGRAM_CHAT_ID")
