# Vera Open — Setup Guide
Version: 0.5.0

Complete setup from zero to first briefing.

---

## Canonical flow

```
Step 1 → Install Python 3.11+, Git, uv
Step 2 → Fork and clone the repo
Step 3 → Get credentials (Notion, Telegram, Claude)
Step 4 → Run vera setup wizard
Step 5 → First briefing
Step 6 → Enable automation (GitHub Actions)
```

---

## Step 1 — Prerequisites (5 min)

Install:

### Python 3.11+
- **Windows:** python.org/downloads — check "Add to PATH" during install
- **macOS:** `brew install python` or download from python.org
- **Linux:** `sudo apt install python3 python3-pip`

### Git
- **Windows:** git-scm.com/download/win
- **macOS:** `brew install git`
- **Linux:** `sudo apt install git`

### uv (package manager)
- **Windows (PowerShell):** `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS/Linux:** `curl -LsSf https://astral.sh/uv | sh`

### Verify
```
python --version    # 3.11+
git --version
uv --version
```

---

## Step 2 — Fork and clone (5 min)

1. Go to https://github.com/veralifeos/vera-open
2. Click Fork → create fork under your account
3. Clone your fork:
```
git clone https://github.com/YOUR_USERNAME/vera-open.git
cd vera-open
uv sync
```

---

## Step 3 — Get your credentials (15 min)

You need 4 things:

### Notion token
1. notion.so → Settings → Connections → Develop or manage integrations
2. New integration → name "Vera" → Internal → Read+Insert+Update
3. Save → copy token (starts with `ntn_` or `secret_`)

### Notion template
1. Open: https://same-tiger-545.notion.site/Vera-Life-OS-31b487bf2603816aba1df400b86dbde3
2. Click Duplicate → copy to your workspace
3. For each database (Tasks, Pipeline, etc.): open it → ••• → Connections → Connect to → Vera

**Important:** Connect the integration on each DATABASE individually, not on the parent page.

### Telegram bot
1. Telegram → @BotFather → `/newbot`
2. Follow prompts → copy token (format: `7xxx:AAH...`)
3. Send one message to your bot (any text)
4. Open `https://api.telegram.org/botYOUR_TOKEN/getUpdates` → find `chat.id` number

### Claude API key
1. console.anthropic.com → create account (US$5 free credit)
2. API Keys → Create Key → copy (starts with `sk-ant-api03-`)

---

## Step 4 — Run setup wizard (5 min)

```
uv run vera setup
```

The wizard asks for all credentials and generates `config/config.yaml` and `config/.env` automatically.

### Validate connections:
```
uv run vera validate
```

### Full diagnostic (if validate shows issues):
```
uv run vera doctor
```

Expected output: all `[OK]` checks.

**validate vs doctor:**
- `validate` = quick preflight (config + secrets + connections)
- `doctor` = deep diagnostic with 10 checks and `[OK]/[WARN]/[FAIL]` output

---

## Step 5 — First briefing (2 min)

### Test locally (no Telegram, no state saved):
```
uv run vera briefing --dry-run --force
```

If a briefing text appears in the terminal, everything is working.

### Send real briefing:
```
uv run vera briefing --force
```

Check Telegram — your bot should send a message.

---

## Step 6 — Enable automation (5 min)

1. Go to your fork on GitHub
2. Settings → Secrets and variables → Actions
3. Add 4 repository secrets:
   - `NOTION_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Actions tab → find "Vera Briefing" workflow → Enable workflow

From now on, Vera runs automatically at the scheduled time (default: 12:00 UTC / 09:00 BRT on weekdays).

Weekend workflows are also included:
- Saturday: weekly review with retrospective
- Sunday: feedback loop analysis

---

## Next steps

- Edit `workspace/USER.md` with your real priorities — this dramatically improves briefing quality
- Install research packs: `uv run vera packs install jobs`
- Customize persona: edit `workspace/AGENT.md` (optional)
- Explore commands: `uv run vera --help`
- Stuck? Ask the Vera Setup Assistant or visit getvera.dev/setup
