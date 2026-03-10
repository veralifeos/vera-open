# Docker Setup

Run Vera with a single command. No Python installation required.

## Quick Start

```bash
git clone https://github.com/veralifeos/vera-open.git
cd vera-open

# Configure
cp config/config.example.yaml config/config.yaml
cp .env.example .env
# Edit both files with your tokens

# Build
docker compose build

# Validate config
docker compose run --rm vera validate

# Test with dry run
docker compose run --rm vera briefing --dry-run

# Run for real
docker compose run --rm vera briefing
```

## Commands

```bash
# Daily briefing
docker compose run --rm vera briefing
docker compose run --rm vera briefing --dry-run
docker compose run --rm vera briefing --force

# Research packs
docker compose run --rm vera research news --dry-run
docker compose run --rm vera research jobs --dry-run
docker compose run --rm vera research financial --dry-run
docker compose run --rm vera research --list

# Validate config and connections
docker compose run --rm vera validate

# Interactive setup wizard
docker compose run --rm -it vera setup
```

## Scheduled Runs (cron)

Add to your host's crontab (`crontab -e`):

```bash
# Daily briefing at 9:00 AM
0 9 * * * cd /path/to/vera-open && docker compose run --rm vera briefing >> /var/log/vera.log 2>&1

# Research before briefing
50 8 * * * cd /path/to/vera-open && docker compose run --rm vera research news >> /var/log/vera.log 2>&1
55 8 * * * cd /path/to/vera-open && docker compose run --rm vera research jobs >> /var/log/vera.log 2>&1
58 8 * * * cd /path/to/vera-open && docker compose run --rm vera research financial >> /var/log/vera.log 2>&1
```

## Build Options

### Default (slim, ~300MB)

```bash
docker compose build
```

### With embeddings (better scoring, ~2GB)

```bash
docker compose build --build-arg INSTALL_EXTRAS=embeddings-light
```

Or for full sentence-transformers:

```bash
docker compose build --build-arg INSTALL_EXTRAS=embeddings
```

### With financial extras (SEC EDGAR)

```bash
docker compose build --build-arg INSTALL_EXTRAS=financial
```

## Persistent State

State is persisted via volume mounts:

| Path | Content | Purpose |
|---|---|---|
| `./state/` | Briefing history, dedup, last run | Survives container restarts |
| `./config/` | config.yaml, pack configs | Your configuration |
| `./workspace/` | AGENT.md, USER.md | Persona and personal context |

## Troubleshooting

**Build fails**: Make sure Docker and Docker Compose are installed. Run `docker compose build --no-cache` for a clean build.

**"config not found"**: Ensure `config/config.yaml` exists. Copy from `config/config.example.yaml`.

**"env var not set"**: Check `.env` file exists and contains required tokens.

**Validate connections**: `docker compose run --rm vera validate`

**View logs**: `docker compose logs vera`

**Shell access**: `docker compose run --rm --entrypoint bash vera`
