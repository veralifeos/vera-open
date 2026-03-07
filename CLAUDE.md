# CLAUDE.md -- Vera Open

## O que e
Vera Open e um Life Operating System open-source que le databases Notion, gera briefings diarios via LLM (Claude ou Ollama), e entrega via Telegram.

## Stack
Python 3.11+, uv, Typer CLI, Pydantic v2, aiohttp, aiolimiter, tenacity, Google Calendar API (opcional)

## Estrutura
```
vera/                    # Core package
  backends/              # StorageBackend ABC + NotionBackend
  llm/                   # LLMProvider ABC + ClaudeProvider + OllamaProvider
  domains/               # Domain ABC + Tasks, Pipeline, Contacts (auto-registry)
  modes/briefing.py      # Pipeline: collect -> delta -> rank -> context -> generate
  integrations/          # telegram.py (chunking + 3-level fallback), calendar.py
  config.py              # Pydantic models, YAML loader, env var resolution
  state.py               # StateManager (delta, mention_counts, zombies, idempotency)
  personas.py            # Executive/coach presets com regras de escalacao
  briefing_history.py    # Circular buffer (5 entries, 200 words) anti-repeticao
  source_health.py       # Monitora fontes com zeros consecutivos
  last_run.py            # Observabilidade por execucao
  cli.py                 # Typer: setup, validate, briefing
tests/                   # 170+ testes, zero chamadas externas
config/config.example.yaml
workspace/AGENT.example.md
workspace/USER.example.md
```

## Convencoes
- PT-BR para dominio (nomes de funcoes em dominios, personas, briefings)
- Ingles para infra (classes, utils, docs tecnicos)
- Naming: snake_case everywhere, classes PascalCase
- Async por default em backends e integracoes

## Testes
uv run pytest tests/ -- ~170 testes, zero chamadas externas, tudo mockado

## O que NAO fazer
- Importar Notion ou Anthropic fora dos modulos especificos (backends/notion.py, llm/claude.py)
- Quebrar a abstracao StorageBackend/LLMProvider no briefing.py
- Adicionar dependencias sem necessidade clara
- Commit sem testes passando

## Backlog futuro
- Research mode (watchers framework, job search como pack)
- Health, Finances, Learning domains
- Multi-backend (Airtable, Supabase)
- Bidirectional Telegram
- Weekly scoring recalibration
