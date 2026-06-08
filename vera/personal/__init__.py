"""Modulos pessoais — bot Telegram bidirecional e astrologia.

EXCECAO de arquitetura: este pacote importa Notion e Anthropic diretamente,
fora das abstracoes backends/ e llm/. Isso e intencional — e codigo pessoal
portado do vera-private, com calls sync simples e binding a databases Notion
especificos do Fernando. Nao generalizar sem necessidade.

Dependencias opcionais (install via `uv sync --group personal`):
  - pyswisseph (calculos astrologicos)
  - anthropic (Claude Haiku pra interpretacao)
  - requests (Telegram API)
"""
