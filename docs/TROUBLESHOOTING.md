# Troubleshooting

Common issues and how to fix them.

---

## Config Errors

### `Config file not found at 'config.yaml'`

You haven't created your config file yet.

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your values
```

### `tasks.database_id is required`

Your Tasks database ID is empty in `config.yaml`. Find your database ID:

1. Open the database as a full page in Notion
2. Copy the URL: `notion.so/workspace/<database_id>?v=...`
3. Paste the 32-character hex string into `config.yaml`

### `tasks.database_id should be 32 hex characters`

The ID you pasted isn't the right length. Common mistakes:
- You copied the full URL instead of just the ID
- You copied a page ID instead of the database ID
- You included the `?v=...` part

### `daily_check is enabled but database_id is empty`

Either set the database_id or disable it:
```yaml
daily_check:
  enabled: false
```

### `Urgency weights must sum to 1.0`

The four weights under `scoring.urgency_weights` must add up to exactly 1.0.

### `persona.preset is 'custom' but no custom_prompt provided`

If you set `preset: "custom"`, you must also provide `custom_prompt`:
```yaml
persona:
  preset: "custom"
  custom_prompt: "Your custom system prompt here..."
```

---

## Environment Variables

### `Missing required environment variables`

Set all four secrets:
```bash
export NOTION_TOKEN=ntn_...
export ANTHROPIC_API_KEY=sk-ant-...
export TELEGRAM_BOT_TOKEN=1234567890:ABC...
export TELEGRAM_CHAT_ID=123456789
```

For local development, create a `.env` file in the project root or `config/` directory. Vera auto-loads it on startup — no need to `export` manually.

**Windows users:** If your `.env` was created with Notepad or another Windows editor, it may have a UTF-8 BOM (byte order mark) that makes the first variable unreadable. Vera handles this automatically with `utf-8-sig` encoding, but if you see issues, re-save the file as "UTF-8 without BOM".

For GitHub Actions, add them as repository secrets (Settings → Secrets → Actions).

### `NOTION_TOKEN doesn't start with 'ntn_'`

You might be using an old-format token or a session cookie. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) and create a new integration.

### `TELEGRAM_CHAT_ID must be numeric`

The chat ID is a number, not your username. To find it:
1. Send `/start` to your bot on Telegram
2. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Look for `"chat":{"id":123456789}`

---

## Notion API Errors

### `Notion API 401 (unauthorized)`

Your integration token is invalid or expired. Regenerate it at [notion.so/my-integrations](https://www.notion.so/my-integrations).

### `Notion API 404 (object_not_found)`

The database exists but your integration doesn't have access. Fix:

1. Open the database in Notion
2. Click `•••` (top right) → **Connections**
3. Click **Connect to** → select your integration

### `Notion API 400 (validation_error)`

Usually means a property name in `config.yaml` doesn't match your database. Run with `debug.verbose: true` to see the full error. Common causes:
- Typo in property name (case-sensitive!)
- Property type mismatch (e.g., trying to write a number to a text field)
- Property was renamed or deleted in Notion

### `Notion API 400: property type select does not match`

Your Status field uses Notion's built-in **Status** type, but Vera defaults to querying it as a **Select**. Add this to your config:

```yaml
domains:
  tasks:
    fields:
      status_filter_type: "status"   # default is "select"
```

Most PT-BR Notion templates use `select`. Check your database: if the Status column shows colored dots with "Not started / In progress / Done", it's the built-in Status type.

### `Rate limited (429). Waiting...`

Vera handles this automatically with exponential backoff. If you see it frequently, you may have too many parallel operations. This is rare with normal usage.

### `Failed after 3 attempts`

Notion's servers are having issues. Wait a few minutes and try again. If persistent, check [status.notion.so](https://status.notion.so).

---

## Claude API Errors

### `401 Unauthorized` / `invalid_api_key`

Your Anthropic API key is wrong. Check it at [console.anthropic.com](https://console.anthropic.com).

### `429 Rate Limit`

You've hit Anthropic's rate limit. This shouldn't happen with normal daily usage (1-2 calls/day). If it does, you may be on a free trial with strict limits.

### `overloaded_error`

Claude's servers are busy. The pipeline will fail, and you can retry by running the GitHub Actions workflow manually.

---

## Telegram Errors

### `Telegram API error (401)`

Your bot token is invalid. Create a new bot with @BotFather and update the token.

### `Telegram API error (400): chat not found`

The chat ID is wrong, or your bot hasn't been started. Send `/start` to your bot on Telegram, then try again.

### `HTML parse failed, sending as plain text`

The AI generated invalid HTML. Vera automatically falls back to plain text. If this happens often, check your custom persona prompt — it may not be instructing proper HTML output.

### `SSLCertVerificationError` / SSL handshake fails

If you're behind a corporate proxy, VPN, or antivirus that intercepts HTTPS (e.g., Kaspersky, Zscaler), Telegram API calls will fail with SSL errors.

**Fix:** Set `VERA_SSL_VERIFY=0` in your `.env` file. This disables SSL verification for Telegram and validate commands. Only use this for local development — GitHub Actions doesn't need it.

### Message not received

1. Check that you sent `/start` to your bot
2. Verify chat ID is correct
3. Check GitHub Actions logs for errors
4. Try `debug.dry_run: false` and `debug.verbose: true` locally

---

## GitHub Actions

### Workflow never runs

1. Make sure the workflow file is at `.github/workflows/daily.yml`
2. Check that Actions are enabled (Settings → Actions → General)
3. GitHub disables scheduled workflows on repos with no activity for 60 days. Push any commit to re-enable.

### Workflow runs but fails

Check the Actions log:
1. Go to your repo → **Actions** tab
2. Click the failed run
3. Expand the step that failed
4. Common issue: secrets not set (Settings → Secrets → Actions)

### Briefing arrives 15-20 minutes late

This is normal. GitHub Actions cron has documented delays of 5-20 minutes. It's not a bug.

### `config.yaml not found` in GitHub Actions

The CI workflows use `config/config.ci.yaml` (tracked in the repo), not the gitignored `config.yaml`. The workflow sets `VERA_CONFIG=config/config.ci.yaml` as an env var. If you need to customize CI config, edit `config.ci.yaml` directly.

### `git push` fails with 403 in CI

The workflow needs write permission to commit state files. Ensure your workflow has:
```yaml
permissions:
  contents: write
```

### State files not committed in CI

The `state/` directory is gitignored. Use `git add -f state/` to force-add it in CI.

---

## Performance

### Pipeline takes more than 60 seconds

With verbose logging (`debug.verbose: true`), check which phase is slow:
- **Collectors:** Usually fast (<5s). If slow, you may have thousands of tasks.
- **Urgency update:** Each task = 1 API call. 100 tasks ≈ 15s.
- **AI synthesis:** Claude typically responds in 3-10s.
- **Telegram:** Near-instant.

For large task databases (500+), consider adding a stricter filter in `config.yaml` (e.g., only fetch tasks from the current month).

---

## Research Packs

### Research returns 0 results

Without `sentence-transformers` installed, scoring uses keyword-only mode. This is normal — Vera logs a warning once and rebalances weights automatically.

If you get 0 results:
- Check that your pack config keywords match actual job titles / article content
- Lower `relevance_threshold` (e.g., 0.25 for financial, 0.3 for news)
- Run with `--force` to bypass idempotency
- Use `--dry-run` first to see scores without saving state

### Scoring seems too low

The keyword scorer uses coverage-based scoring: `sqrt(coverage) * (0.6 + 0.4 * intensity)`. With many keywords, each individual keyword contributes less to coverage. Keep keyword lists focused (5-15 terms) rather than exhaustive.

---

## Still stuck?

1. Run with full verbose logging:
   ```bash
   # In config.yaml, set:
   # debug:
   #   verbose: true
   python -m vera briefing --force
   ```

2. Check each component independently:
   ```bash
   python -m vera validate   # Config OK?
   # If validate passes, the issue is in runtime (API calls)
   ```

3. Open an issue on GitHub with the error log (redact your tokens!).
