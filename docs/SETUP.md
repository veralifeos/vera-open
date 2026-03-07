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
pip install -e .
# or: uv pip install -e .
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

```bash
# Load env vars (if using .env manually)
export $(cat .env | xargs)

# Validate everything is connected
python -m vera validate

# Test without sending Telegram or saving state
python -m vera briefing --dry-run --force

# Run for real
python -m vera briefing --force
```

## 10. Deploy to GitHub Actions

1. Fork the repository (or push your configured copy)
2. Go to **Settings** -> **Secrets and variables** -> **Actions**
3. Add these repository secrets:

| Secret | Value |
|---|---|
| `NOTION_TOKEN` | Your Notion integration token |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

4. Create `.github/workflows/daily.yml`:

```yaml
name: Vera Daily Briefing
on:
  schedule:
    - cron: '0 12 * * *'  # 09:00 BRT (UTC-3)
  workflow_dispatch:

jobs:
  briefing:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e .
      - run: python -m vera briefing
        env:
          NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          FORCE_RUN: "true"
```

5. To test: go to **Actions** -> **Vera Daily Briefing** -> **Run workflow**

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
