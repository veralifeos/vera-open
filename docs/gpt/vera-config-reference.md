# Vera Open — config.yaml Reference
Version: 0.5.0

The main configuration file lives at `config/config.yaml`. It is created by `vera setup` and can be edited manually at any time.

Secrets (tokens, API keys) live in `config/.env` — never in config.yaml.

---

## Full example

```yaml
# Vera Open — config.yaml

meta:
  name: "Your Name"
  language: "pt-BR"          # or "en"
  timezone: "America/Sao_Paulo"

backend:
  type: notion
  notion:
    token_env: NOTION_TOKEN   # env var name, not the token itself

llm:
  default: claude
  providers:
    claude:
      model: claude-sonnet-4-6
      api_key_env: ANTHROPIC_API_KEY
    ollama:
      model: llama3.2
      base_url: http://localhost:11434

delivery:
  telegram:
    bot_token_env: TELEGRAM_BOT_TOKEN
    chat_id_env: TELEGRAM_CHAT_ID

schedule:
  briefing: "07:00"
  briefing_window_hours: 4
  weekly: "saturday 08:00"
  feedback: "sunday 17:00"

domains:
  tasks:
    enabled: true
    collection: "YOUR_TASKS_DATABASE_ID"
  pipeline:
    enabled: true
    collection: "YOUR_PIPELINE_DATABASE_ID"
  contacts:
    enabled: false
    collection: "YOUR_CONTACTS_DATABASE_ID"
  check:
    enabled: true
    collection: "YOUR_CHECK_DATABASE_ID"
  finances:
    enabled: false
    collection: "YOUR_FINANCES_DATABASE_ID"
  learning:
    enabled: false
    collection: "YOUR_LEARNING_DATABASE_ID"

research:
  enabled: true
  packs:
    news:
      enabled: true
      config_path: config/packs/news.yaml
    jobs:
      enabled: true
      config_path: config/packs/jobs.yaml
    financial:
      enabled: false
      config_path: config/packs/financial.yaml
    custom:
      enabled: false
      config_path: config/packs/custom.yaml

debug:
  dry_run: false
  log_level: INFO
```

---

## Sections

### meta

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Your name, used in briefing greetings |
| `language` | string | `pt-BR` or `en` — affects briefing language |
| `timezone` | string | IANA timezone (e.g. `America/Sao_Paulo`, `Europe/London`, `US/Eastern`) |

### backend

Only `notion` is supported currently. Future: Airtable, Supabase.

| Key | Description |
|-----|-------------|
| `type` | Always `notion` |
| `notion.token_env` | Name of the env var containing your Notion token |

### llm

| Key | Description |
|-----|-------------|
| `default` | Which provider to use: `claude` or `ollama` |
| `providers.claude.model` | Claude model string |
| `providers.claude.api_key_env` | Env var name for Anthropic API key |
| `providers.ollama.model` | Ollama model name |
| `providers.ollama.base_url` | Ollama server URL |

**Available Claude models:**
- `claude-sonnet-4-6` — recommended default, best quality (~$0.02-0.03/day)
- `claude-haiku-4-5-20251001` — faster, cheaper (~$0.01/day), slightly lower quality

### delivery

| Key | Description |
|-----|-------------|
| `telegram.bot_token_env` | Env var name for Telegram bot token |
| `telegram.chat_id_env` | Env var name for Telegram chat ID |

### schedule

| Key | Description |
|-----|-------------|
| `briefing` | Time for daily briefing (24h format, e.g. `"07:00"`) |
| `briefing_window_hours` | How many hours after scheduled time Vera will still run |
| `weekly` | Day and time for weekly review (e.g. `"saturday 08:00"`) |
| `feedback` | Day and time for feedback loop analysis (e.g. `"sunday 17:00"`) |

Note: GitHub Actions cron times are in UTC. Convert from your timezone.

### domains

Each domain corresponds to a Notion database. Set `enabled: true` and provide the `collection` (database ID).

| Domain | Purpose | Required? |
|--------|---------|-----------|
| `tasks` | To-do list with status, priority, deadline | **Yes** |
| `pipeline` | Opportunities, applications, deals | No |
| `contacts` | People and relationship tracking | No |
| `check` | Weekly self-assessment (Check Semanal, 0-10 scores) | No |
| `finances` | Income and expenses | No |
| `learning` | Courses, books, articles | No |

To find a database ID: open the database in Notion → copy URL → the ID is the 32-character string before `?v=`.

The `vera setup` wizard can auto-detect database IDs.

### research

| Key | Description |
|-----|-------------|
| `enabled` | Master switch for all research packs |
| `packs.{name}.enabled` | Enable/disable individual pack |
| `packs.{name}.config_path` | Path to the pack's YAML config file |

Manage packs with `vera packs` commands — they update this section automatically.

### debug

| Key | Description |
|-----|-------------|
| `dry_run` | Set `true` to always run in dry-run mode |
| `log_level` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

---

## config/.env

Secrets file. Created by `vera setup`. Never commit to git (it's in `.gitignore`).

```
NOTION_TOKEN=ntn_xxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxx
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789

# Optional
RAPIDAPI_KEY=your_key_here
JOOBLE_API_KEY=your_key_here
SERPAPI_KEY=your_key_here
```

---

## Research pack YAML reference

Pack configs live in `config/packs/{name}.yaml`. Manage with `vera packs` CLI.

### news.yaml

```yaml
topics:
  - name: "AI & Tech"
    keywords: [artificial intelligence, LLM, product launch]
    sources:
      - type: rss
        name: TechCrunch
        url: https://techcrunch.com/feed/

scoring:
  relevance_threshold: 0.4
  weights:
    keyword: 0.5
    embedding: 0.5

dedup:
  ttl_days: 7
```

### jobs.yaml

```yaml
criteria:
  keywords: [product manager, growth, CRO, RevOps]
  seniority: [senior, lead, principal]
  location: remote
  salary_min: 8000
  stack: [HubSpot, GA4, Figma]
  exclude_keywords: [junior, internship, unpaid]

sources:
  himalayas:
    enabled: true
  remoteok:
    enabled: true
  jsearch:
    enabled: true
    api_key_env: RAPIDAPI_KEY

scoring:
  relevance_threshold: 0.5
  use_llm_scoring: false

dedup:
  ttl_days: 14
```

### custom.yaml

```yaml
pack_label: "My Monitor"
keywords: [keyword1, keyword2]
keywords_boost: [bonus1, bonus2]
exclude_keywords: [irrelevant1]

sources:
  - type: rss
    name: Source Name
    url: https://example.com/feed
    enabled: true
  - type: web_search
    name: Web Search
    engine: duckduckgo
    query: "search query here"
    enabled: true

scoring:
  relevance_threshold: 0.35
  weights:
    keyword: 0.6
    embedding: 0.4

dedup:
  ttl_days: 14
```

### Pack management workflow

| Intent | Command |
|--------|---------|
| Install pack (copy YAML template + enable) | `uv run vera packs install <n>` |
| Enable already-installed pack | `uv run vera packs enable <n>` |
| Disable without deleting config | `uv run vera packs disable <n>` |
| Execute pack | `uv run vera research <n>` |
| Test pack without saving state | `uv run vera research <n> --dry-run` |
| Show pack details | `uv run vera packs info <n>` |
