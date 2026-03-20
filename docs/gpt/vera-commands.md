# Vera Open — CLI Command Reference
Version: 0.5.0

All commands use `uv run vera` as the standard prefix.
Alternative: activate the venv first, then use `vera` directly.

---

## vera setup
```
uv run vera setup              # Interactive configuration wizard
```
Creates `config/config.yaml` and `config/.env` with your credentials.
Run once after cloning, or again to reconfigure.

## vera validate
```
uv run vera validate           # Test config, secrets, and live connections
```
Quick preflight check. Run after setup to verify everything connects.

## vera doctor
```
uv run vera doctor             # Full diagnostic — 10 checks with [OK]/[WARN]/[FAIL]
```
Deeper than validate. Run when validate fails or when the problem is unclear.
Checks: Python, .env, config.yaml, Notion token, databases, Telegram bot, Telegram chat ID, LLM, state directory, USER.md.

**When to use which:**
- `validate` first (quick preflight)
- `doctor` when validate fails or you need detailed diagnostics

---

## vera briefing
```
uv run vera briefing                  # Daily briefing (respects time window)
uv run vera briefing --force          # Skip time window and idempotency check
uv run vera briefing --dry-run        # Test without sending Telegram or saving state
uv run vera briefing --dry-run --force # Recommended for first test
uv run vera briefing --weekly         # Weekly review with retrospective and metrics
```

---

## vera research
```
uv run vera research news             # Run news pack
uv run vera research jobs             # Run jobs pack
uv run vera research financial        # Run financial pack
uv run vera research custom           # Run custom pack
uv run vera research --list           # List available packs
uv run vera research --all            # Run all enabled packs in parallel
uv run vera research jobs --dry-run   # Test without saving dedup state
uv run vera research jobs --force     # Ignore dedup, re-process everything
```

---

## vera packs
```
uv run vera packs list                # Show all packs: name, install status, enabled, description
uv run vera packs install news        # Copy example YAML → active config, enable in config.yaml
uv run vera packs install jobs --no-enable  # Install without enabling
uv run vera packs enable financial    # Enable an installed pack
uv run vera packs disable news        # Disable without removing config file
uv run vera packs info jobs           # Show description, status, and YAML content
```

**Workflow for a new pack:**
1. `vera packs install <name>` — copies template YAML and enables it
2. Edit `config/packs/<name>.yaml` — customize keywords, sources, thresholds
3. `vera research <name> --dry-run` — test it
4. Results appear in RADAR section of next briefing

---

## vera feedback
```
uv run vera feedback analyze          # Run behavioral analysis, write inferences to USER.md
uv run vera feedback status           # Show observation count and active inferences
uv run vera feedback clear            # Remove all active inferences, reset state
```

The feedback loop detects 5 behavioral signals:
- **carga** — average energy < 5 in recent briefings
- **prioridade_real** — task completed after 4+ mentions
- **zona_morta** — task with 7+ mentions, never completed
- **pack_irrelevante** — pack with 0 results in 5+ consecutive runs
- **ritmo** — 80%+ completions on same weekday

Minimum 5 briefings before any inference fires. Max 15 active inferences.
Runs automatically via GitHub Actions every Sunday at 17:00 BRT.

---

## vera status
```
uv run vera status                    # System health overview: last run, tasks, zombies, source alerts
```

## vera bot
```
uv run vera bot                       # Start Telegram polling bot (responds to /status, /next, /help)
```

---

## Global options
```
uv run vera --version                 # Show version (v0.5.0)
uv run vera --help                    # Show all commands
uv run vera <command> --help          # Show help for specific command
```

---

## Environment variables (config/.env)

Required:
```
NOTION_TOKEN=ntn_...
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=7xxx:AAH...
TELEGRAM_CHAT_ID=123456789
```

Optional:
```
RAPIDAPI_KEY=your_key_here           # For JSearch job source
JOOBLE_API_KEY=your_key_here         # For Jooble job source
SERPAPI_KEY=your_key_here            # For SerpAPI web search in custom packs
VERA_SSL_VERIFY=0                    # Disable SSL verification if needed
PYTHONIOENCODING=utf-8               # Fix Windows encoding issues
```
