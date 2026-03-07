# Vera

**AI-powered Life Operating System. Open source.**

Vera reads your Notion workspace, calculates what matters most, and sends you a daily briefing via Telegram. No app to open, no dashboard to check. Your priorities arrive where you already are.

It runs on GitHub Actions (free tier) and costs ~$0.01-0.03/day in AI API usage. Zero infrastructure to maintain.

---

## What it does

- **Task prioritization** — reads your Notion tasks, scores urgency (deadline + priority + staleness), ranks what matters today
- **State tracking** — remembers what was mentioned before, detects new/worsening tasks, identifies zombie tasks stuck for weeks
- **Pipeline monitoring** — tracks opportunities, job applications, or deals across stages
- **Contact management** — surfaces relationships that need follow-up
- **Calendar awareness** — pulls today's events from Google Calendar (optional)
- **Daily briefing** — generates a concise, personalized briefing via Claude or Ollama
- **Telegram delivery** — sends the briefing with chunking, retry, and error alerting
- **Weekend modes** — Saturday retrospective, Sunday strategic planning

## How it works

```
Notion databases ──> Domain collectors ──> State engine ──> LLM ──> Telegram
   (tasks,              (parallel)         (delta,        (Claude    (chunked,
    pipeline,                               mentions,      or         retried)
    contacts)                               zombies)       Ollama)
                              |                               |
                         Google Calendar                 Persona preset
                          (optional)                   (executive/coach)
```

The state engine tracks every task across runs: what's new, what worsened, what's been stuck. Mention counts escalate tone automatically (normal -> suggest actions -> stop mentioning -> zombie cooldown). This prevents the briefing from nagging about the same tasks forever.

## Quick start

```bash
# 1. Clone
git clone https://github.com/veralifeos/vera-open.git
cd vera-open

# 2. Install
pip install -e .
# or: uv pip install -e .

# 3. Run the setup wizard
python -m vera setup
# Creates config.yaml and .env with your Notion token, API keys, etc.

# 4. Validate everything works
python -m vera validate

# 5. Test with a dry run (no Telegram, no state saved)
python -m vera briefing --dry-run --force

# 6. Run for real
python -m vera briefing --force

# 7. (Optional) Tell Vera about yourself
cp workspace/USER.example.md workspace/USER.md
# Edit USER.md — makes briefings dramatically better
```

For the full setup guide including Telegram bot creation and GitHub Actions deployment, see [docs/SETUP.md](docs/SETUP.md).

## Notion template

Vera works with any Notion setup as long as you have a Tasks database. If you're starting fresh, duplicate the template:

**[Duplicate the Vera template](LINK_AQUI)**

| Database | Purpose | Required? |
|---|---|---|
| **Tasks** | To-do list with status, priority, deadline | Yes |
| **Pipeline** | Opportunities, applications, deals | No |
| **Contacts** | People and relationship tracking | No |
| **Health** | Exercise, sleep, mood logs | No |
| **Finances** | Income and expenses | No |
| **Learning** | Courses, books, articles | No |

See [docs/NOTION_TEMPLATE.md](docs/NOTION_TEMPLATE.md) for database schemas and field mapping.

## Requirements

| Service | What you need | Cost |
|---|---|---|
| **Notion** | Free account + Integration token | Free |
| **Anthropic** | API key (Claude Sonnet) | ~$0.01-0.03/day |
| **Telegram** | Bot token + your Chat ID | Free |
| **GitHub** | Repository with Actions enabled | Free (2,000 min/mo) |
| **Python** | 3.11+ | -- |

Ollama can replace Anthropic for a fully free, local setup.

## Configuration

Vera is config-driven. Everything lives in `config.yaml`:

- **Backend** -- where your data lives (Notion, future: Airtable, Supabase)
- **LLM** -- which AI generates briefings (Claude, Ollama, future: OpenAI)
- **Domains** -- which life areas to track (tasks required, rest optional)
- **Persona** -- `executive` (direct, ironic) or `coach` (supportive), or custom via `workspace/AGENT.md`
- **Schedule** -- briefing time, weekend modes
- **Integrations** -- Google Calendar (optional)

See [config/config.example.yaml](config/config.example.yaml) for all options with comments.

## Project structure

```
vera-open/
├── vera/                    # Core package
│   ├── backends/            # StorageBackend ABC + NotionBackend
│   ├── llm/                 # LLMProvider ABC + Claude + Ollama
│   ├── domains/             # Domain ABC + Tasks, Pipeline, Contacts
│   ├── modes/               # Briefing pipeline (collect → analyze → generate)
│   ├── integrations/        # Telegram, Google Calendar
│   ├── config.py            # Pydantic models + YAML loader
│   ├── state.py             # State management (delta, mentions, zombies)
│   ├── personas.py          # Executive/coach prompt presets
│   ├── briefing_history.py  # Anti-repetition (circular buffer of past briefings)
│   ├── source_health.py     # Data source monitoring
│   ├── last_run.py          # Observability per execution
│   └── cli.py               # Typer CLI (setup, validate, briefing)
├── workspace/               # User-specific files (gitignored)
│   ├── AGENT.example.md     # Persona template
│   └── USER.example.md      # Personal context template
├── config/
│   └── config.example.yaml  # Full configuration reference
├── state/                   # Persisted state (gitignored in production)
├── tests/                   # 170+ tests, zero external calls
└── docs/
    ├── SETUP.md             # Step-by-step setup guide
    └── NOTION_TEMPLATE.md   # Database schemas
```

## How Vera thinks

**Urgency score** -- weighted combination of:
- **Deadline proximity** (40%) -- past-due = max score, today = high, next week = medium
- **Priority level** (25%) -- maps your priority labels (Alta/Media/Baixa) to score
- **Staleness** (20%) -- mention count penalty (tasks mentioned 4+ times lose priority)
- **Dependencies** (15%) -- reserved for v0.2

**Priority tiers:**
- **Overdue** -- past deadline, always surfaces
- **Top priority** -- highest scored active tasks (max 20 sent to LLM)
- **Zombie** -- mentioned 8+ times without status change, enters cooldown
- **Cooldown** -- temporarily hidden from briefing (7 days)

**Mention count escalation:**
- 1-3x: normal tone
- 4-6x: suggests concrete actions to unblock
- 7x: "I'll stop mentioning this until you tell me what to do"
- 8+: zombie cooldown, excluded from briefing

## Modes

| Command | What it does |
|---|---|
| `vera setup` | Interactive wizard -- creates config.yaml and .env |
| `vera validate` | Checks config, secrets, backend connection, LLM |
| `vera briefing` | Full briefing pipeline (respects time window) |
| `vera briefing --dry-run` | Runs pipeline without sending Telegram or saving state |
| `vera briefing --force` | Ignores time window guard and idempotency check |

## Troubleshooting

**"Fora da janela"** -- Vera only runs within 3h before / 2h after your configured briefing time. Use `--force` to override.

**"Abortando (idempotencia)"** -- Same data as last run. Use `--force` or wait for data to change.

**No Telegram message** -- Run `vera validate` to check bot token and chat ID. Check that `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set.

**Notion connection fails** -- Ensure the integration has access to each database (Share -> Add connection).

## Roadmap

**v0.1.0** (current)
- [x] Daily briefing pipeline with state management
- [x] Notion backend with auto-discovery
- [x] Multi-LLM support (Claude + Ollama)
- [x] Google Calendar integration (optional)
- [x] Configurable personas (executive/coach/custom)
- [x] Retry with exponential backoff on all integrations
- [x] 3-level error alerting via Telegram
- [x] 3 life domains: Tasks, Pipeline, Contacts
- [x] Setup wizard + validation
- [x] 170+ tests

**v0.2** (planned)
- [ ] Research mode (job search, market monitoring)
- [ ] Health, Finances, Learning domains
- [ ] Bidirectional Telegram (reply to mark done, reschedule)
- [ ] Weekly scoring with trend analysis

**v0.3** (future)
- [ ] Multi-backend (Airtable, Supabase)
- [ ] Custom scoring formulas
- [ ] Dependency tracking between tasks
- [ ] Web dashboard

## License

Apache 2.0 -- fork it, customize it, make it yours.

---

*Built for people who want their productivity system to talk to them, not the other way around.*
