# Changelog

All notable changes to Vera Open.

## [0.3.0] — 2026-03-11

### Added

- **`vera research --all`** — runs all available research packs in parallel via `asyncio.gather`. One pack failure doesn't block others. CI daily workflow now uses a single step instead of three.
- **`vera briefing --weekly`** — dedicated weekly review mode with:
  - Completed task collection from Notion (cross-referenced with state for recency)
  - Weekly metrics: completed, open, new, zombies, briefing count
  - Structured LLM prompt: retrospective → open items → patterns → next week priorities
  - Works on any day (not just Saturday), triggered manually or via CI
- **`vera status`** — system health dashboard showing last run, task counts, zombies, cooldowns, research pack dedup stats, and source health alerts
- **`vera bot`** — polling-based Telegram bot that responds to commands:
  - `/status` — system status (last run, tasks, zombies, high-mention tasks)
  - `/next` — top 3 priority tasks (excludes zombies and cooldowns)
  - `/help` — list available commands
- `TasksDomain.collect_completed()` method for querying done tasks
- `vera/research/retry.py` — shared retry configuration for all research HTTP calls
- 16 new tests (334 total)

### Changed

- CI daily workflow: 3 research steps → 1 (`research --all --force`)
- CI weekly workflow: `briefing --force` → `briefing --weekly --force`
- Research sources import `RETRY_KWARGS` from shared module (was duplicated in 3 files)
- Version bump: 0.2.1 → 0.3.0

## [0.2.1] — 2026-03-11

Full smoke test: every bug found in the end-to-end pipeline was fixed in this release.

### Fixed

- **Notion 400 on select/status filter** — Databases using Notion's `select` type for Status fields (common in PT-BR templates) got a 400 error. Added configurable `status_filter_type` field (default: `"select"`). Set to `"status"` if your DB uses Notion's built-in Status type. (`vera/domains/tasks.py`)
- **Telegram SSL error behind proxy/antivirus** — `SSLCertVerificationError` on machines with intercepting proxies. Set `VERA_SSL_VERIFY=0` to bypass. (`vera/integrations/telegram.py`, `vera/cli.py`)
- **`.env` not auto-loaded** — Added `python-dotenv` dependency. CLI now calls `load_dotenv()` on startup. (`vera/cli.py`, `pyproject.toml`)
- **Windows BOM in `.env`** — Files saved as UTF-8 with BOM on Windows broke the first variable. Fixed with `encoding="utf-8-sig"`. (`vera/cli.py`)
- **Scoring returns 0 without embedder** — When `sentence-transformers` is not installed, keyword scores were diluted by a 0.5 embedding fallback. Now rebalances to keyword-only scoring automatically. Warning logged once. (`vera/research/scoring.py`, `vera/research/packs/jobs/scorer.py`)
- **`_parse_date` crash on int timestamps** — Himalayas and Arbeitnow APIs return unix timestamps as integers. Added `isinstance(date_str, int)` branch. (`vera/research/packs/jobs/sources.py`, `vera/research/packs/financial/sources.py`)
- **DeFiLlama `None < float` crash** — `raw.get("tvl", 0)` returns `None` when key exists with null value. Fixed with `or 0` pattern. (`vera/research/packs/financial/sources.py`)
- **Dead Reuters RSS feed** — DNS failure on Reuters URL. Replaced with CNBC Economy feed. (`config/packs/financial.example.yaml`)
- **GitHub Actions CI failures** — Complete rewrite of workflows:
  - Created `config/config.ci.yaml` (tracked) instead of relying on gitignored `config.yaml`
  - `uv` instead of `pip` for faster installs
  - `git add -f state/` for gitignored state directory
  - `permissions: contents: write` for state commits
  - Correct entrypoints (`python -m vera` not `python -m src.main`)
- **`config.example.yaml` field names** — Aligned with PT-BR Notion template (accented characters: Estágio, Próximo Passo, etc.)

### Changed

- Research pack example configs use broader keywords and lower thresholds for better out-of-box results
- Test count: 300 → 309

### Added

- `python-dotenv` as a dependency
- `config/config.ci.yaml` for GitHub Actions
- `VERA_SSL_VERIFY` environment variable for SSL bypass

## [0.2.0] — 2026-03-10

Research Pack framework with 3 built-in packs.

- Research Pack ABC + registry with auto-discovery
- News Pack (RSS feeds, keyword + embedding scoring, topic grouping)
- Job Search Pack (9 sources, 10-dimension scorer, Notion auto-save)
- Financial Pack (Finnhub, SEC EDGAR, CoinGecko, DeFiLlama)
- Deduplication engine with TTL persistence
- LLM synthesis for topic summarization
- RADAR section in daily briefings
- 300+ tests

## [0.1.0] — 2026-03-08

Initial public release.

- Daily briefing pipeline with state management
- Notion backend with auto-discovery
- Multi-LLM support (Claude + Ollama)
- Google Calendar integration (optional)
- Configurable personas (executive/coach/custom)
- 3 life domains: Tasks, Pipeline, Contacts
- Telegram delivery with chunking, retry, 3-level error alerting
- Setup wizard + validation CLI
