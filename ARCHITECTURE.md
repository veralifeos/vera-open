# Architecture

## System overview

```
                           +-------------------------+
                           |       config.yaml        |
                           |   (Pydantic validated)   |
                           +-----------+-------------+
                                       |
                   +-------------------+-------------------+
                   |                   |                   |
             +-----v-----+     +------v------+    +------v------+
             |  Storage   |     |    LLM      |    |  Integra-   |
             |  Backend   |     |  Provider   |    |   tions     |
             |  (Notion)  |     |(Claude/     |    |(Telegram,   |
             |            |     | Ollama)     |    | Calendar)   |
             +-----+------+     +------+------+    +------+------+
                   |                   |                   |
             +-----v------------------v-------------------v-----+
             |                Briefing Pipeline                   |
             |  collect -> delta -> rank -> context -> generate   |
             +---------------------+-----------------------------+
                                   |
                   +---------------+---------------+
                   |               |               |
             +-----v-----+  +-----v-----+  +-----v-----+
             |   State    |  |  History   |  |  last_run  |
             | (Git-first)|  |  (buffer)  |  |  (metrics) |
             +------------+  +-----------+  +------------+
```

## Core abstractions

### StorageBackend (`vera/backends/base.py`)

```python
class StorageBackend(ABC):
    async def query(collection_id, filters, sorts, max_pages) -> list[dict]
    async def query_parallel(queries) -> dict[str, list[dict]]
    async def create_record(collection_id, properties) -> dict
    async def update_record(record_id, properties) -> dict
    def extract_text(record) -> str
```

Implementations: `NotionBackend` (aiohttp + aiolimiter 3 req/s + tenacity retry).

### LLMProvider (`vera/llm/base.py`)

```python
class LLMProvider(ABC):
    async def generate(system_prompt, user_prompt, max_tokens, temperature) -> str
    async def generate_structured(system_prompt, user_prompt, schema, max_tokens) -> dict
```

Implementations: `ClaudeProvider` (Anthropic SDK), `OllamaProvider` (HTTP localhost:11434).

### Domain (`vera/domains/base.py`)

```python
class Domain(ABC):
    async def collect() -> dict       # Fetch raw data from backend
    def analyze(data) -> dict         # Extract insights
    def context(data, analysis) -> str # Generate text for LLM prompt
```

Implementations: `TasksDomain`, `PipelineDomain`, `ContactsDomain`, `CheckSemanalDomain`.

### StateManager (`vera/state.py`)

```python
class StateManager:
    def load() -> dict
    def save(state, dry_run) -> bool
    def compute_hash(payload) -> str           # MD5, 12 chars
    def is_duplicate(state, hash, today) -> bool
    def update_mention_counts(state, tasks, delta) -> dict
    def get_zombies(state, threshold) -> list[str]
    def compute_delta(state, current_tasks, today) -> dict
    def build_snapshot(tasks) -> dict
```

State is Git-first: `briefing_state.json` committed to repo for persistence across CI runs.

## Briefing pipeline

The pipeline in `vera/modes/briefing.py` executes these steps:

1. **Load config** -- Pydantic validation from YAML
2. **Time window guard** -- only runs within configured hours (skip with `--force`)
3. **Load state** -- previous run data from `state/vera_state.json`
4. **Collect domains** -- parallel data fetch from all enabled domains
5. **Load workspace** -- AGENT.md, USER.md from workspace/
5.5. **Research packs** -- skip vagas already applied (dedup TTL 30 days)
6. **Compute hash** -- MD5 of current payload for idempotency
7. **Idempotency check** -- skip if same date or same hash (skip with `--force`)
8. **Compute delta** -- new tasks, removed tasks, worsened deadlines
9. **Update mention counts** -- increment counters for mentioned tasks
10. **Identify zombies** -- tasks mentioned 8+ times without change
11. **Filter and rank** -- exclude zombies/cooldown, sort by urgency score
12. **Fetch calendar** -- Google Calendar events if enabled
13. **Build context** -- structured text with tasks, delta, zombies, domains, calendar, Check Semanal
14. **Load history** -- past briefings for anti-repetition
15. **Generate via LLM** -- persona prompt + context + day-specific instructions
16. **Persist** -- save state, history, last_run metrics; send via Telegram

## Notion structure

### Core databases
- **Acoes Taticas** -- ~21 active tasks. No "Semana" field. 5 relation columns by client (Proj. PMMV, Proj. Leticia, Proj. Trem Bao, Proj. Vera, Proj. Urbba)
- **Check Semanal** -- weekly self-assessment with numbers 0-10 (Energia, Vida Pratica, Carreira, Sanidade) + Highlight
- **Pipeline** -- opportunities and job applications
- **Contatos & Network** -- relationship tracking

### Client structure (Paralelos)
Hierarchical: Client > Projects. Each client has a sub-database "Projetos [Cliente]" with standardized schema (Projeto, Status, Tipo, Prioridade, Inicio, Prazo, Valor, Faturamento, Contato, Notas, Acoes Taticas).

5 project databases: Projetos PMMV, Projetos Leticia, Projetos Trem Bao, Projetos Vera, Projetos Urbba.

## State management

### Delta detection
Compares current task snapshot with previous run:
- **novas** -- tasks not in previous snapshot
- **removidas** -- tasks in previous snapshot but not current
- **pioraram** -- tasks whose deadline moved earlier

### Mention counts escalation (5 tiers)
Each task has a counter incremented per briefing appearance:
- 1x: normal tone
- 2-3x: cites if relevant
- 4-6x: suggest concrete unblocking actions
- 7x: "I'll stop mentioning this until you tell me what to do"
- 8+: zombie status, 7-day cooldown

### Zombie cooldown
Tasks mentioned 8+ times without status/deadline change enter cooldown. They are excluded from the briefing for 7 days, then re-evaluated.

### Idempotency
Prevents duplicate briefings via:
- Same calendar date as last run -> skip
- Same payload hash as last run -> skip
- `--force` flag overrides both checks

### Dedup TTL
Research pack deduplication uses 30-day TTL (not 7).

## Config system

Pydantic v2 models in `vera/config.py`. Loading priority:
1. `VERA_CONFIG` env var (path to YAML)
2. `config.yaml` in project root
3. `config/config.yaml`

All sensitive values use env var references (`token_env: "NOTION_TOKEN"`) rather than storing secrets directly.

## Retry and resilience

All external calls use tenacity:
- **3 attempts**, exponential backoff (2s -> 4s -> 8s, max 30s)
- Retries on: `ClientError`, `TimeoutError`, `RateLimitError`, `APIConnectionError`
- `reraise=True` -- final error propagates clearly
- `notificar_erro` fallback for error notification

Error notification (`vera/integrations/telegram.py`):
1. **Level 1**: async Telegram send with retry
2. **Level 2**: sync urllib fallback (no aiohttp dependency)
3. **Level 3**: print to stderr (captured by GitHub Actions)

Time window guard prevents accidental runs outside configured hours.

## Persona system

1. **Presets** (`vera/personas.py`): `executive` (direct, ironic-maternal) and `coach` (supportive, honest)
2. **Custom override**: `workspace/AGENT.md` replaces preset when `persona.preset: custom`
3. **User context**: `workspace/USER.md` injected into system prompt as personal context
4. **Day-specific instructions**: Monday overview, Tuesday-Thursday focus, Friday close-out, Saturday retrospective (analytic with Check Semanal), Sunday planning (strategic with load reduction)

Max words per day: Monday 500, Saturday 400, weekday/Sunday 350.

## Weekend modes

### Saturday (analytic retrospective)
Numbers first: open vs closed tasks, job funnel, Check Semanal interpretation (0-3 red, 4-6 yellow, 7-10 green), scoring health alerts. Trend analysis, not pressure.

### Sunday (strategic planning)
3 concrete priorities for Monday. If Check Semanal average < 5, reduces to 2 priorities and suggests rest. Strategic tone, never motivational.

## Research Packs

7 job sources: Himalayas, Remotive, RemoteOK, Arbeitnow, Jooble, JSearch, Greenhouse, Lever, Ashby. b2b_saas auto-grant + synonyms.

## Modules

- `vera/briefing_history.py` -- circular buffer (5 entries, 200 words) for anti-repetition
- `vera/source_health.py` -- monitors sources with consecutive zeros
- `vera/last_run.py` -- observability per execution

## Event Engine

`vera/event_engine.py` injects personality events into briefings:

- **[PRAISE]** -- factual recognition of real progress (zombie resolved, bulk completions, pipeline advance)
- **[IRONY]** -- dry irony about operational patterns (chronic tasks, missed deadlines, stale follow-ups)
- Guards: max 2 events/week, min 2 days between, suppressed when energy < 4 or avg task score > 80
- State: `state/events.json` tracks week counter, trigger IDs (dedup), last event date
- Integration: `build_event_context()` constructs context dict, `EventEngine.evaluate()` returns `EventResult | None`, signal injected into briefing context before LLM generation

## Feedback Loop

`vera/feedback/` -- automated behavioral analysis (4 layers):

1. **ObservationCollector** (`collector.py`) -- saves one observation per briefing to `state/observations.json`. Schema: tasks_suggested, tasks_completed, energy_score, dia_num, pack_results, mention_counts_snapshot, task_titles. Keeps last 90 days.

2. **BehaviorTracker** (`tracker.py`) -- detects 5 behavioral signals (minimum 5 observations):
   - `carga`: avg energy < 5 in last 7 days with 3+ briefings
   - `prioridade_real`: task completed after 4+ mentions
   - `zona_morta`: task with 7+ mentions, never completed
   - `pack_irrelevante`: pack with 0 results in 5+ consecutive runs
   - `ritmo`: 80%+ completions on same weekday across 14+ days

3. **PatternEngine** (`patterns.py`) -- converts signals to inferences (rule-based, no LLM). v1 generates for carga, prioridade_real, zona_morta. Dedup by type+target (stable across weeks). Expiry: 30 days.

4. **UserProfileWriter** (`writer.py`) -- writes ONLY to `## Feedback loop` section of `workspace/USER.md`. Preserves manual content (calibrations, notes). Max 15 active inferences. Each inference: `- [inferido YYYY-MM-DD] {text}` with "remova esta linha se discordar".

## Packs CLI

`vera/packs_cli.py` -- Typer sub-app for research pack management:
- `vera packs list` -- table with pack name, config status, enabled status, description
- `vera packs install <name>` -- copies example YAML to active config, enables in config.yaml
- `vera packs enable/disable <name>` -- toggles without deleting config
- `vera packs info <name>` -- shows description, status, and YAML content

## Testing strategy

- **428 tests**, all in `tests/`
- **Zero external calls** -- everything mocked (AsyncMock, MagicMock, patch)
- **Fixture patterns**: `_minimal_config()`, `MockBackend`, `MockLLM`, `tmp_path` for state files
- **Coverage**: config, backends, LLM providers, domains (tasks, pipeline, contacts, check_semanal), state, briefing history, last_run, briefing pipeline, CLI, retry, Telegram, Calendar, workspace, source health, personas, event engine, feedback loop, end-to-end
- Run with: `uv run pytest tests/`

## Workflows

- `daily.yml` -- research --all + briefing (daily, 12:00 UTC)
- `weekly.yml` -- briefing --weekly (Saturday, 13:00 UTC)
- `feedback.yml` -- feedback loop analysis (Sunday, 20:00 UTC)
