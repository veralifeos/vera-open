# Architecture

## System overview

```
                           ┌─────────────────────────┐
                           │       config.yaml        │
                           │   (Pydantic validated)   │
                           └────────────┬────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              ┌─────▼─────┐     ┌──────▼──────┐    ┌──────▼──────┐
              │  Storage   │     │    LLM      │    │  Integra-   │
              │  Backend   │     │  Provider   │    │   tions     │
              │  (Notion)  │     │(Claude/     │    │(Telegram,   │
              │            │     │ Ollama)     │    │ Calendar)   │
              └─────┬──────┘     └──────┬──────┘    └──────┬──────┘
                    │                   │                   │
              ┌─────▼──────────────────▼───────────────────▼─────┐
              │                Briefing Pipeline                   │
              │  collect → delta → rank → context → generate      │
              └─────────────────────┬─────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
              │   State    │  │  History   │  │  last_run  │
              │   (.json)  │  │  (buffer)  │  │  (metrics) │
              └────────────┘  └───────────┘  └────────────┘
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

Implementations: `TasksDomain`, `PipelineDomain`, `ContactsDomain`.

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

## Briefing pipeline

The pipeline in `vera/modes/briefing.py` executes these steps:

1. **Load config** -- Pydantic validation from YAML
2. **Time window guard** -- only runs within configured hours (skip with `--force`)
3. **Load state** -- previous run data from `state/vera_state.json`
4. **Collect domains** -- parallel data fetch from all enabled domains
5. **Load workspace** -- AGENT.md, USER.md from workspace/
6. **Compute hash** -- MD5 of current payload for idempotency
7. **Idempotency check** -- skip if same date or same hash (skip with `--force`)
8. **Compute delta** -- new tasks, removed tasks, worsened deadlines
9. **Update mention counts** -- increment counters for mentioned tasks
10. **Identify zombies** -- tasks mentioned 8+ times without change
11. **Filter and rank** -- exclude zombies/cooldown, sort by urgency score
12. **Fetch calendar** -- Google Calendar events if enabled
13. **Build context** -- structured text with tasks, delta, zombies, domains, calendar
14. **Load history** -- past briefings for anti-repetition
15. **Generate via LLM** -- persona prompt + context + day-specific instructions
16. **Persist** -- save state, history, last_run metrics; send via Telegram

## State management

### Delta detection
Compares current task snapshot with previous run:
- **novas** -- tasks not in previous snapshot
- **removidas** -- tasks in previous snapshot but not current
- **pioraram** -- tasks whose deadline moved earlier

### Mention counts escalation
Each task has a counter incremented per briefing appearance:
- 1-3x: normal tone
- 4-6x: suggest concrete unblocking actions
- 7x: announce stopping mentions
- 8+: zombie status, 7-day cooldown

### Zombie cooldown
Tasks mentioned 8+ times without status/deadline change enter cooldown. They are excluded from the briefing for 7 days, then re-evaluated.

### Idempotency
Prevents duplicate briefings via:
- Same calendar date as last run -> skip
- Same payload hash as last run -> skip
- `--force` flag overrides both checks

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

Error notification (`vera/integrations/telegram.py`):
1. **Level 1**: async Telegram send with retry
2. **Level 2**: sync urllib fallback (no aiohttp dependency)
3. **Level 3**: print to stderr (captured by GitHub Actions)

Time window guard prevents accidental runs outside configured hours.

## Persona system

1. **Presets** (`vera/personas.py`): `executive` (direct, ironic-maternal) and `coach` (supportive, honest)
2. **Custom override**: `workspace/AGENT.md` replaces preset when `persona.preset: custom`
3. **User context**: `workspace/USER.md` injected into system prompt as personal context
4. **Day-specific instructions**: Monday overview, Tuesday-Thursday focus, Friday close-out, Saturday retrospective, Sunday planning

Max words per day: Monday 500, Saturday 400, weekday/Sunday 350.

## Testing strategy

- **170+ tests**, all in `tests/`
- **Zero external calls** -- everything mocked (AsyncMock, MagicMock, patch)
- **Fixture patterns**: `_minimal_config()`, `MockBackend`, `MockLLM`, `tmp_path` for state files
- **Coverage**: config, backends, LLM providers, domains, state, briefing history, last_run, briefing pipeline, CLI, retry, Telegram, Calendar, workspace, source health, personas, end-to-end
- Run with: `uv run pytest tests/`
