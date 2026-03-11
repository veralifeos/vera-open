# CLAUDE.md -- Vera Open

## O que e
Vera Open e um Life Operating System open-source que le databases Notion, gera briefings diarios via LLM (Claude ou Ollama), e entrega via Telegram. Inclui framework de Research Packs para monitorar noticias, vagas e financeiro com scoring inteligente.

## Stack
Python 3.11+, uv, Typer CLI, Pydantic v2, aiohttp, aiolimiter, tenacity, httpx, feedparser, Google Calendar API (opcional), sentence-transformers/light-embed (opcional), edgartools (opcional)

## Estrutura
```
vera/                    # Core package
  backends/              # StorageBackend ABC + NotionBackend
  llm/                   # LLMProvider ABC + ClaudeProvider + OllamaProvider
  domains/               # Domain ABC + Tasks, Pipeline, Contacts, CheckSemanal (auto-registry)
  modes/briefing.py      # Pipeline: collect -> delta -> rank -> context -> generate + RADAR
  integrations/          # telegram.py (chunking + 3-level fallback), calendar.py
  research/              # Research Pack framework
    base.py              # ResearchPack ABC, ResearchItem, ResearchResult
    sources/             # Source ABC + RSSSource (conditional GET) + APISource (pagination)
    scoring.py           # 3-layer: keywords (TF-IDF), embeddings (graceful), LLM
    dedup.py             # TTL-based JSON persistence per pack (30 days TTL)
    synthesis.py         # LLM topic summarization
    registry.py          # PackRegistry singleton, auto-discovery
    packs/
      news/              # NewsResearchPack — RSS feeds, topic grouping
      jobs/              # JobSearchPack — 9 sources, 10-dim scorer, Notion save
      financial/         # FinancialResearchPack — earnings, SEC, crypto, DeFi
  config.py              # Pydantic models, YAML loader, env var resolution
  state.py               # StateManager (delta, mention_counts, zombies, idempotency)
  personas.py            # Executive/coach presets com regras de escalacao (5 faixas)
  briefing_history.py    # Circular buffer (5 entries, 200 words) anti-repeticao
  source_health.py       # Monitora fontes com zeros consecutivos
  last_run.py            # Observabilidade por execucao
  cli.py                 # Typer: setup, validate, briefing, research, status, bot, feedback
tests/                   # 359 testes, zero chamadas externas
config/config.example.yaml
config/packs/            # news.example.yaml, jobs.example.yaml, financial.example.yaml
workspace/AGENT.example.md
workspace/USER.example.md
docs/RESEARCH_PACKS.md   # Guia completo dos Research Packs
docs/CREATING_PACKS.md   # Como criar packs customizados
```

## Convencoes
- PT-BR para dominio (nomes de funcoes em dominios, personas, briefings)
- Ingles para infra (classes, utils, docs tecnicos)
- Naming: snake_case everywhere, classes PascalCase
- Async por default em backends e integracoes
- httpx para todo HTTP novo (research), aiohttp para backends legado
- BYOK pattern: API keys ausentes desabilitam fontes silenciosamente

## Testes
uv run pytest tests/ -- 359 testes, zero chamadas externas, tudo mockado

## CLI
- `vera briefing` — gera briefing diario (--weekly para review semanal)
- `vera research <pack>` — executa pack de research (--dry-run, --force, --list, --all)
- `vera status` — mostra saude do sistema
- `vera bot` — inicia bot Telegram (polling, responde /status /next /help)
- `vera feedback` — analisa accuracy do briefing (--save para persistir)
- `vera validate` — valida config
- `vera setup` — wizard interativo

## O que NAO fazer
- Importar Notion ou Anthropic fora dos modulos especificos (backends/notion.py, llm/claude.py)
- Quebrar a abstracao StorageBackend/LLMProvider no briefing.py
- Adicionar dependencias sem necessidade clara
- Commit sem testes passando
- Remover FINANCIAL_DISCLAIMER do financial pack (hardcoded, obrigatorio)
- Referenciar nomes pessoais no codigo (zero hardcoded)

## Sessoes recentes

### Sessoes 18-19
- Sugestao de acoes concretas 4-6x (escalacao mention_counts)
- vera feedback em producao (67% accuracy, 75% precision, 82% recall)
- +3 close titles no jobs pack
- Marcos x tarefas, alerta Mapeada parada, estimativa salarial
- Funil no sabado, domingo estrategico
- Feedback loop mensal

### Sessao 20
- Check Semanal: numbers 0-10 (Energia, Vida Pratica, Carreira, Sanidade)
- Interpretacao no sabado (faixas vermelho/amarelo/verde, tendencia, cruzamentos)
- Ajuste de carga no domingo (media < 5 = 2 prioridades em vez de 3)
- Notion: reestruturacao completa
  - Paralelos > Projetos por cliente (5 databases)
  - Acoes Taticas: campo Semana removido, 5 relations por cliente, ~21 tarefas ativas
  - Check Diario virou Check Semanal
  - Sistema Blip arquivado, databases legados deletados
- 359 testes
