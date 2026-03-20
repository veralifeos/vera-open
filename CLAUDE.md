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
  modes/briefing.py      # Pipeline: collect -> delta -> rank -> context -> generate + RADAR + events
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
      custom/            # CustomResearchPack — pack generico configuravel via YAML
  feedback/              # Feedback loop automatico
    collector.py         # ObservationCollector — 1 obs por briefing, state/observations.json
    tracker.py           # BehaviorTracker — 5 sinais (carga, prioridade_real, zona_morta, pack_irrelevante, ritmo)
    patterns.py          # PatternEngine — sinais → inferencias (rule-based, sem LLM)
    writer.py            # UserProfileWriter — escreve APENAS em ## Feedback loop do USER.md
    loop.py              # Orquestrador: collector → tracker → patterns → writer
  event_engine.py        # EventEngine — [PRAISE] e [IRONY] no briefing (max 2/semana)
  config.py              # Pydantic models, YAML loader, env var resolution
  state.py               # StateManager (delta, mention_counts, zombies, idempotency)
  personas.py            # Executive/coach presets com regras de escalacao + eventos
  packs_cli.py           # Typer sub-app: vera packs list/install/enable/disable/info
  briefing_history.py    # Circular buffer (5 entries, 200 words) anti-repeticao
  source_health.py       # Monitora fontes com zeros consecutivos
  last_run.py            # Observabilidade por execucao
  cli.py                 # Typer: setup, validate, briefing, research, status, bot, feedback, packs
tests/                   # 428 testes, zero chamadas externas
config/config.example.yaml
config/packs/            # news, jobs, financial, custom (.example.yaml)
workspace/AGENT.example.md
workspace/USER.example.md
docs/                    # SETUP, CUSTOMIZE, RESEARCH_PACKS, CREATING_PACKS, etc.
.github/workflows/       # daily.yml, weekly.yml, feedback.yml
```

## Convencoes
- PT-BR para dominio (nomes de funcoes em dominios, personas, briefings)
- Ingles para infra (classes, utils, docs tecnicos)
- Naming: snake_case everywhere, classes PascalCase
- Async por default em backends e integracoes
- httpx para todo HTTP novo (research), aiohttp para backends legado
- BYOK pattern: API keys ausentes desabilitam fontes silenciosamente

## Testes
uv run pytest tests/ -- 428 testes, zero chamadas externas, tudo mockado

## CLI
- `vera briefing` — gera briefing diario (--weekly para review semanal)
- `vera research <pack>` — executa pack de research (--dry-run, --force, --list, --all)
- `vera packs list|install|enable|disable|info` — gerencia research packs
- `vera feedback analyze|status|clear` — feedback loop automatico
- `vera status` — mostra saude do sistema
- `vera bot` — inicia bot Telegram (polling, responde /status /next /help)
- `vera validate` — valida config
- `vera setup` — wizard interativo
- `vera doctor` — diagnostico com 10 checks

## O que NAO fazer
- Importar Notion ou Anthropic fora dos modulos especificos (backends/notion.py, llm/claude.py)
- Quebrar a abstracao StorageBackend/LLMProvider no briefing.py
- Adicionar dependencias sem necessidade clara
- Commit sem testes passando
- Remover FINANCIAL_DISCLAIMER do financial pack (hardcoded, obrigatorio)
- Referenciar nomes pessoais no codigo (zero hardcoded)

## Sessoes recentes

### Sessao 21 (v0.5.0)
- Event engine: [PRAISE] e [IRONY] com guards (2/semana, min 2 dias entre)
- Feedback loop: collector → tracker (5 sinais) → patterns → writer (## Feedback loop only)
- User priority scoring: parse_user_priorities() + boost no scoring
- vera packs CLI: list/install/enable/disable/info
- Custom research pack
- Personas reescritas: operadora pessoal executiva + instrucoes de eventos
- USER.example.md expandido: feedback loop, calibracoes, dominios ativos
- Landing page getvera.dev (GitHub Pages + Cloudflare Worker para leads)
- 428 testes

### Sessoes 18-20
- Sugestao de acoes concretas 4-6x (escalacao mention_counts)
- Check Semanal: numbers 0-10 (Energia, Vida Pratica, Carreira, Sanidade)
- Interpretacao no sabado, ajuste de carga no domingo
- Notion: reestruturacao completa (Paralelos > Projetos, Blip arquivado)
- vera setup overhaul, vera doctor, config presets
