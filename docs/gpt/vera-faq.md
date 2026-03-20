# Vera Open — FAQ & Troubleshooting Guide

This document is the primary knowledge base for the Vera Setup Assistant.
Last updated: 2026-03-20 | Version: 0.5.0

---

## GENERAL

**Q: What is Vera Open?**
Vera Open is a local-first personal briefing system. Every morning, it pulls your tasks from Notion, searches for jobs/news/financial data, synthesizes everything with Claude AI, and delivers a single briefing to your Telegram. You set it up once, and it runs automatically via GitHub Actions — no server required.

**Q: What's new in v0.5.0?**
- Event Engine — personality events ([PRAISE] and [IRONY]) injected into briefings based on real progress or patterns
- Feedback Loop — automated behavioral analysis that detects 5 signals and writes inferences to USER.md
- User Priority Scoring — priorities from USER.md boost matching tasks in ranking
- `vera packs` CLI — manage research packs (list, install, enable, disable, info)
- Custom Research Pack — generic YAML-based monitor for any RSS feeds
- Persona rewrite with event integration instructions
- Landing page at getvera.dev with lead capture
- 428 tests

**Q: Is Vera Open free?**
The software is free and open source (Apache 2.0). You'll pay only for:
- Claude API (Anthropic): ~US$0.01–0.03 per briefing day. New accounts get US$5 free credit.
- GitHub Actions: free for public repositories (2,000 min/month).
- Notion: free plan is sufficient.
- Telegram: free.

**Q: Do I need to know how to code?**
You don't need to write code. But you need to be comfortable running commands in a terminal. The `vera setup` wizard handles most of the configuration interactively.

**Q: What operating systems are supported?**
Windows 10+, macOS 12+, and Linux (Ubuntu 20.04+). All commands work on all three.

**Q: Is my data private?**
Yes. Vera runs on your own GitHub account and connects to your own Notion workspace. Your data never goes through any Vera server. The only external service that processes your content is the Claude API (Anthropic).

---

## PREREQUISITES & INSTALLATION

**Q: What do I need before starting?**
1. Python 3.11 or higher
2. Git
3. uv (Python package manager)
4. A Notion account (free)
5. A Telegram account
6. An Anthropic account (for Claude API key)

**Q: How do I install Python?**
- Windows: Download from https://python.org/downloads — check "Add to PATH" during install
- macOS: `brew install python` or download from python.org
- Linux: `sudo apt install python3 python3-pip`

Verify: `python --version` — should show 3.11+

**Q: How do I install uv?**

Windows (PowerShell):
```
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

macOS / Linux:
```
curl -LsSf https://astral.sh/uv | sh
```

Verify: `uv --version`

**Q: How do I fork and clone the repository?**
1. Go to https://github.com/veralifeos/vera-open
2. Click "Fork" (top right) → create fork under your GitHub account
3. Clone:
```
git clone https://github.com/YOUR_USERNAME/vera-open.git
cd vera-open
uv sync
```

**Q: What does `uv sync` do?**
Installs all Python dependencies into a local virtual environment. Run once after cloning, and again after any `git pull`.

---

## SETUP WIZARD

**Q: How do I run the setup wizard?**
```
uv run vera setup
```

The wizard asks for your name, Notion token, Telegram credentials, and Claude API key. It generates config/config.yaml and config/.env automatically.

**Q: Can I edit the config manually?**
Yes. Open config/config.yaml in any text editor. See config/config.example.yaml for all options.

---

## NOTION SETUP

**Q: How do I get a Notion Integration Token?**
1. Go to https://notion.so
2. Settings → Connections → Develop or manage integrations
3. Click "New integration" — name it "Vera" — Internal type
4. Capabilities: Read + Insert + Update content
5. Save → copy the token (starts with `ntn_` or `secret_`)

**Q: How do I connect the integration to my databases?**
After duplicating the template, for each database:
1. Open the database in Notion
2. Click ••• (three dots) top right
3. Connections → Connect to → select "Vera"

**Important:** Connect the integration on the DATABASE itself, not on a parent page. Open each database directly and connect from there.

Do this for: Tasks, Pipeline, Contacts, Check Semanal, and any other databases you want Vera to read.

**Q: Where is the Notion template?**
https://same-tiger-545.notion.site/Vera-Life-OS-31b487bf2603816aba1df400b86dbde3
Click "Duplicate" to copy it to your workspace.

**Q: How do I find database IDs?**
Open the database in Notion. The ID is in the URL:
`notion.so/DATABASE_ID?v=VIEW_ID`
Copy the 32-character string before the `?v=`

The `vera setup` wizard can auto-detect database IDs if the integration is connected.

---

## TELEGRAM SETUP

**Q: How do I create a Telegram bot?**
1. Open Telegram → search @BotFather
2. Send `/newbot`
3. Choose name and username (must end in "bot")
4. Copy the token BotFather gives you (format: `7123456789:AAH...`)

**Q: How do I find my Chat ID?**
1. Send any message to your bot (any text, just to initialize)
2. Open in browser: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
3. Find `"chat":{"id": 123456789}` — that number is your Chat ID

If getUpdates returns empty: send another message to the bot first, then reload the URL.

---

## ANTHROPIC / CLAUDE API

**Q: How do I get a Claude API key?**
1. Go to https://console.anthropic.com
2. Create account (free — US$5 credit on signup)
3. API Keys → Create Key
4. Copy the key (starts with `sk-ant-api03-`)

**Q: How much does it cost?**
~US$0.01–0.03 per briefing. The US$5 free credit lasts several months of daily use.

**Q: Which model does Vera use?**
`claude-sonnet-4-6` by default. Change in config.yaml under `llm.providers.claude.model`.

Other option: `claude-haiku-4-5-20251001` — faster and cheaper, slightly lower quality.

**Q: Can I use Ollama instead?**
Yes. Set `llm.default: ollama` in config.yaml and configure the Ollama section. Requires Ollama running locally. This makes Vera fully free (no API costs).

---

## GITHUB ACTIONS

**Q: How do I set up automatic daily briefings?**
1. Your fork → Settings → Secrets and variables → Actions
2. Add 4 repository secrets:
   - `NOTION_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Actions tab → find "Vera Briefing" workflow → Enable workflow

**Q: What time does it run?**
Default: 12:00 UTC (09:00 BRT) on weekdays. Change the cron in `.github/workflows/daily.yml`.

Weekend workflows:
- `weekly.yml` — Saturday 13:00 UTC (weekly review with retrospective)
- `feedback.yml` — Sunday 20:00 UTC (feedback loop analysis)

**Q: How do I test before enabling automation?**
```
uv run vera briefing --dry-run --force   # no Telegram, no state changes
uv run vera briefing --force              # sends to Telegram
```

---

## VERA CLI COMMANDS

### Core
```
vera setup              # Interactive setup wizard
vera validate           # Test config, secrets, connections (preflight)
vera doctor             # Full diagnostic with [OK]/[WARN]/[FAIL] (10 checks)
vera status             # System health overview
vera bot                # Start Telegram polling bot
```

### Briefing
```
vera briefing                  # Daily briefing (respects time window)
vera briefing --force          # Skip time window and idempotency
vera briefing --dry-run        # Test without sending or saving state
vera briefing --weekly         # Weekly review with retrospective
```

### Research Packs
```
vera research news             # Run news pack
vera research jobs             # Run jobs pack
vera research --list           # List available packs
vera research --all            # Run all packs in parallel
vera research jobs --dry-run   # Test without saving state
```

### Pack Management
```
vera packs list                # Show all packs and status
vera packs install news        # Install and enable a pack
vera packs enable financial    # Enable installed pack
vera packs disable news        # Disable without removing config
vera packs info jobs           # Show details and current config
```

### Feedback Loop
```
vera feedback analyze          # Run behavioral analysis, update USER.md
vera feedback status           # Show observations and active inferences
vera feedback clear            # Reset all inferences
```

---

## RESEARCH PACKS

**Q: What are Research Packs?**
Modular intelligence modules that monitor the internet for you. They collect, score, deduplicate, and synthesize information from multiple sources. Results appear as a RADAR section in your daily briefing.

**Q: What packs are available?**

| Pack | Sources | What it monitors |
|------|---------|-----------------|
| **news** | RSS/Atom feeds | Topics you define (AI, geopolitics, etc.) |
| **jobs** | 9 job boards | Job listings matching your criteria |
| **financial** | Finnhub, SEC, CoinGecko, DeFiLlama | Earnings, filings, crypto, DeFi |
| **custom** | Any RSS feeds | Anything you configure via YAML |

**Q: How do I enable a pack?**
```
uv run vera packs install jobs        # install + enable
uv run vera research jobs --dry-run   # test it
```

**Q: How do I configure a pack?**
Edit the pack's YAML file in `config/packs/`. Each pack has different options (keywords, sources, thresholds). See `config/packs/*.example.yaml` for templates.

---

## EVENT ENGINE

**Q: What is the Event Engine?**
A system that injects personality events into briefings based on real data:
- **[PRAISE]** — factual recognition of progress (zombie resolved, bulk completions, pipeline advance)
- **[IRONY]** — dry irony about patterns (chronic tasks, missed deadlines, stale follow-ups)

Guards: max 2 events/week, min 2 days between, suppressed when energy is low.

**Q: Can I disable it?**
Events are generated automatically when conditions are met. They're woven into the briefing naturally — not a separate section.

---

## FEEDBACK LOOP

**Q: What is the Feedback Loop?**
An automated system that analyzes your behavior over time (minimum 5 briefings) and writes inferences to the `## Feedback loop` section of `workspace/USER.md`.

It detects 5 signals: overload (carga), real priorities, dead zones, irrelevant packs, and weekday patterns.

**Q: How do I use it?**
```
uv run vera feedback analyze   # run analysis manually
uv run vera feedback status    # check observations and inferences
uv run vera feedback clear     # reset everything
```

It also runs automatically via GitHub Actions every Sunday at 17:00 BRT.

Each inference includes "remova esta linha se discordar" — delete any line you disagree with.

---

## USER.MD — PERSONALIZATION

**Q: What is workspace/USER.md?**
Your personal profile. Vera reads it to understand your priorities and context. More specific = more relevant briefings.

**Q: What sections should I fill?**
- `## Situacao atual` — current professional situation
- `## Prioridades do mes` — top 3-5 priorities (Vera uses these to boost matching tasks)
- `## Contexto operacional` — active projects, schedule, restrictions
- `## O que NAO quero ouvir` — topics/patterns to suppress
- `## O que QUERO ouvir` — alerts and insights to amplify
- `## Dominios ativos` — which life areas Vera monitors

The `## Feedback loop` section is managed automatically — don't edit it manually (except to remove inferences you disagree with).

---

## TROUBLESHOOTING

**Q: vera doctor fails — how to read output?**
- `[OK]` = working
- `[WARN]` = minor issue, non-blocking
- `[FAIL]` = blocking problem, needs fixing

Common failures:
- `[FAIL] NOTION_TOKEN` — token not set or incorrect in .env
- `[FAIL] Claude API` — key invalid or no credits remaining
- `[FAIL] Telegram` — bot token wrong or chat_id missing
- `[FAIL] Databases` — integration not connected to database (connect via ••• → Connect to)

**Q: "No module named vera" error**
Run `uv sync` first. Always use: `uv run vera ...` (not just `vera ...`)

**Q: Briefing runs but output is generic**
Fill in `workspace/USER.md` with your actual context. Generic output = empty user profile.

**Q: Windows encoding errors (UnicodeDecodeError)**
Add `PYTHONIOENCODING=utf-8` to config/.env. Vera handles BOM in .env since v0.5.0.

**Q: SSL certificate errors**
Set in config/.env: `VERA_SSL_VERIFY=0`

**Q: Notion 400 on status filter**
If using Notion's built-in Status type (not Select), add `status_filter_type: "status"` under `domains.tasks.fields` in config.yaml.

**Q: Research returns 0 results**
- Check pack keywords match actual content
- Lower `relevance_threshold` in pack YAML
- Without `sentence-transformers`, scoring is keyword-only

**Q: "Fora da janela" (outside time window)**
Vera only runs within configured hours. Use `--force` to override.

**Q: "Abortando (idempotencia)"**
Same data as last run. Use `--force` or wait for data to change.

---

## LINKS

- Repository: https://github.com/veralifeos/vera-open
- Landing page: https://getvera.dev
- Setup guide: https://getvera.dev/setup
- Notion template: https://same-tiger-545.notion.site/Vera-Life-OS-31b487bf2603816aba1df400b86dbde3
- Report issues: https://github.com/veralifeos/vera-open/issues
- Anthropic console: https://console.anthropic.com
- Telegram BotFather: https://t.me/BotFather
