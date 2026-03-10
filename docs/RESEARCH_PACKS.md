# Research Packs

Research Packs are modular intelligence modules that monitor external sources, score relevance, deduplicate across runs, and synthesize results into your daily briefing.

## Included Packs

### News/Topic Monitoring (`news`)

Monitors RSS/Atom feeds organized by topics you define. Each topic has its own keywords and feed sources.

**Config:** `config/packs/news.yaml` (copy from `news.example.yaml`)

```bash
python -m vera research news --dry-run
```

Features:
- Keyword + embedding scoring per topic
- Conditional GET (ETag/If-Modified-Since) to minimize bandwidth
- Dedup with 7-day TTL
- LLM synthesis per topic

### Job Search (`jobs`)

Monitors 9 job boards with hybrid 3-layer scoring.

**Config:** `config/packs/jobs.yaml` (copy from `jobs.example.yaml`)

```bash
python -m vera research jobs --dry-run
```

Sources: Himalayas, Remotive, RemoteOK, Arbeitnow, Jooble (free key), JSearch/RapidAPI (paid), Greenhouse, Lever, Ashby.

Features:
- Rule-based scoring (10 dimensions: keywords, location, seniority, salary, stack, etc.)
- Embedding similarity (CV vs job description)
- Optional LLM scoring (Haiku) for top candidates
- Auto-save to Notion Pipeline database
- Dedup with 30-day TTL

### Financial/Investment (`financial`)

Monitors SEC filings, earnings calendars, crypto prices, and financial news.

**Config:** `config/packs/financial.yaml` (copy from `financial.example.yaml`)

```bash
python -m vera research financial --dry-run
```

Sources: Finnhub (earnings, company news), SEC EDGAR via edgartools, CoinGecko (crypto), DeFiLlama (DeFi TVL), financial RSS.

Features:
- BYOK (Bring Your Own Key) — missing keys silently disable the source
- Watchlist-based: stocks by ticker/CIK, crypto by CoinGecko ID
- Category grouping (SEC Filings, Earnings, Crypto, DeFi, News)
- **Mandatory disclaimer** in every output
- Dedup with 3-day TTL

## How to Configure

1. Copy the example config for the pack you want:
   ```bash
   cp config/packs/news.example.yaml config/packs/news.yaml
   ```

2. Edit the YAML file with your topics/criteria/watchlist.

3. Enable in main `config.yaml`:
   ```yaml
   research:
     enabled: true
     packs:
       news:
         enabled: true
         config_path: "config/packs/news.yaml"
   ```

4. Test with dry run:
   ```bash
   python -m vera research news --dry-run
   ```

## Briefing Integration

When research is enabled, results appear as a **=== RADAR ===** section in your daily briefing. Each pack formats its own section.

To disable research without removing configs, set `research.enabled: false` in `config.yaml`.

## API Keys

| Pack | Key | Required? | How to get |
|---|---|---|---|
| News | None | -- | RSS feeds are public |
| Jobs (Jooble) | `JOOBLE_API_KEY` | Optional | jooble.org/api |
| Jobs (JSearch) | `RAPIDAPI_KEY` | Optional | rapidapi.com |
| Financial (Finnhub) | `FINNHUB_API_KEY` | For earnings/news | finnhub.io |
| Financial (CoinGecko) | `COINGECKO_API_KEY` | Optional (demo) | coingecko.com |
| Financial (EDGAR) | None | -- | Public domain |
| Financial (DeFiLlama) | None | -- | Open source |

Missing keys = source silently disabled. The pack still runs with available sources.
