# Setup Guide

Step-by-step guide to get Vera running. From zero to your first briefing in ~20 minutes.

## 1. Prerequisites

- **Python 3.11+** -- check with `python --version`
- **uv** (recommended) -- `pip install uv` or see [docs.astral.sh/uv](https://docs.astral.sh/uv/)
- **git** -- for cloning and state management

## 2. Install

```bash
git clone https://github.com/veralifeos/vera-open.git
cd vera-open
uv sync
# or: pip install -e .
```

## 3. Create Notion integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **"New integration"**
3. Name it "Vera" (or anything you prefer)
4. Under Capabilities, ensure **Read content** is checked
5. Copy the **Internal Integration Secret** (starts with `ntnl_`)

## 4. Connect integration to databases

For each Notion database you want Vera to read:

1. Open the database in Notion
2. Click `...` (top right) -> **Connections** -> **Add connections**
3. Search for "Vera" and add it

**Finding your database ID:**
Open the database as a full page. The URL looks like:
`https://notion.so/workspace/abc123def456...?v=...`
The database ID is the 32-character hex string before `?v=`.

Vera's setup wizard can auto-discover databases shared with the integration.

## 5. Create Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456:ABC-DEF...`)
4. Send any message to your new bot (e.g., `/start`)
5. Get your chat ID by visiting:
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   Find `"chat":{"id":123456789}` in the response. That number is your Chat ID.

## 6. Get Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an account and add credits ($5 minimum)
3. Go to **API Keys** -> **Create Key**
4. Copy the key (starts with `sk-ant-`)

Vera uses Claude Sonnet. Typical cost: $0.01-0.03/day.

## 7. Alternative: Ollama (free, local)

If you prefer a free, local LLM instead of Claude:

```bash
# Install Ollama (see https://ollama.com)
ollama pull llama3.2:3b
```

In config.yaml, set `llm.default: "ollama"`. See config.example.yaml for details.

## 8. Configure

### Option A: Setup wizard (recommended)

```bash
python -m vera setup
```

The wizard walks you through every setting and creates `config.yaml` and `.env`.

### Option B: Manual

```bash
cp config/config.example.yaml config.yaml
```

Edit `config.yaml` with your database IDs, LLM provider, and persona choice.

Create `.env` with your secrets:
```
NOTION_TOKEN=ntnl_your_token_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_CHAT_ID=your_chat_id
```

## 9. First run

Vera auto-loads `.env` from the project root and `config/.env` — no manual `export` needed.

```bash
# Validate everything is connected
python -m vera validate

# Test without sending Telegram or saving state
python -m vera briefing --dry-run --force

# Run for real
python -m vera briefing --force
```

> **Windows users:** If your `.env` was created with Notepad, it may have a UTF-8 BOM that corrupts the first variable. Vera handles this automatically, but if you see issues, re-save as "UTF-8 without BOM".

## 10. Deploy to GitHub Actions

The repo includes pre-built workflows in `.github/workflows/`:
- **`daily.yml`** — runs research packs + briefing every day at 09:00 BRT
- **`weekly.yml`** — runs weekly review on Saturdays at 10:00 BRT

Both use `config/config.ci.yaml` (tracked in the repo) and pull secrets from GitHub Actions.

### Setup

1. Fork the repository (or push your configured copy)
2. Edit `config/config.ci.yaml` with your Notion database IDs
3. Go to **Settings** -> **Secrets and variables** -> **Actions**
4. Add these repository secrets:

| Secret | Required | Value |
|---|---|---|
| `NOTION_TOKEN` | Yes | Your Notion integration token |
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `TELEGRAM_BOT_TOKEN` | Yes | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat ID |
| `JOOBLE_API_KEY` | No | For Jooble job search |
| `RAPIDAPI_KEY` | No | For JSearch job search |
| `FINNHUB_API_KEY` | No | For Finnhub financial data |
| `COINGECKO_API_KEY` | No | For CoinGecko crypto data |

5. To test: go to **Actions** -> **Daily Briefing** -> **Run workflow**

The daily workflow commits state files (`state/`) back to the repo so deduplication persists across runs.

## 11. Customize persona

```bash
cp workspace/AGENT.example.md workspace/AGENT.md
cp workspace/USER.example.md workspace/USER.md
```

- **AGENT.md**: how Vera communicates (tone, rules, limits)
- **USER.md**: who you are (context that makes briefings personal)

Set `persona.preset: custom` in config.yaml to use AGENT.md instead of built-in presets.

## 12. Google Calendar (optional)

Requires the `[calendar]` extra: `pip install -e ".[calendar]"`

1. Create a Google Cloud project and enable the Calendar API
2. Create a service account and download the JSON key
3. Share your calendar with the service account email
4. Set `GOOGLE_CREDENTIALS` env var to the JSON content or file path
5. In config.yaml:

```yaml
integrations:
  google_calendar:
    enabled: true
    credentials_env: "GOOGLE_CREDENTIALS"
    calendar_ids: ["primary"]
```
