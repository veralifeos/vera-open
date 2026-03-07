# Contributing to Vera Open

Thank you for considering contributing to Vera. This guide will help you get started.

## Getting started

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/vera-open.git
cd vera-open

# Install with dev dependencies
pip install -e ".[dev]"
# or with uv:
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/
# or: python -m pytest tests/

# Check code style
uv run ruff check .
uv run ruff format --check .
```

## Development environment

- **Python** 3.11+
- **Package manager**: uv (recommended) or pip
- **Testing**: pytest + pytest-asyncio
- **Linting**: ruff (line length 100, rules: E, F, I, W)
- **Config**: Pydantic v2 models, YAML loader

## Architecture

Vera is built around three core abstractions:

1. **StorageBackend** (`vera/backends/base.py`) -- interface for data access (Notion, future: Airtable, Supabase)
2. **LLMProvider** (`vera/llm/base.py`) -- interface for AI generation (Claude, Ollama, future: OpenAI)
3. **Domain** (`vera/domains/base.py`) -- interface for life domains (Tasks, Pipeline, Contacts)

The briefing pipeline (`vera/modes/briefing.py`) orchestrates everything without importing any concrete backend or LLM directly.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

## Adding a new domain

1. Create `vera/domains/your_domain.py` implementing the `Domain` ABC:
   - `collect()` -- fetch data from backend
   - `analyze()` -- extract insights from raw data
   - `context()` -- generate text for the briefing prompt
2. Register it in `vera/domains/__init__.py` (`_auto_register`)
3. Add config fields in `config/config.example.yaml`
4. Add tests in `tests/test_domains.py`

## Adding a new backend

1. Create `vera/backends/your_backend.py` implementing `StorageBackend`
2. Add factory logic in `vera/cli.py` (`_create_backend`)
3. Add tests in `tests/test_backend_your_backend.py`

## Adding a new LLM provider

1. Create `vera/llm/your_provider.py` implementing `LLMProvider`
2. Add factory logic in `vera/cli.py` (`_create_llm_provider`)
3. Add tests in `tests/test_llm_providers.py`

## Conventions

- **PT-BR** for domain functions, personas, briefing content
- **English** for classes, utilities, infrastructure, technical docs
- **snake_case** for functions and variables, **PascalCase** for classes
- **Async by default** in backends and integrations
- All external calls must have retry (tenacity) with exponential backoff
- Zero direct imports of Notion/Anthropic in briefing pipeline

## PR guidelines

- One feature per PR
- Tests are required for new functionality
- Update docs if behavior changes
- Run `ruff check .` and `ruff format .` before submitting
- Keep PRs focused -- small is better than comprehensive

## Code of conduct

Be respectful. Give constructive feedback. We're building something useful together.

## Questions?

Open an issue at [github.com/veralifeos/vera-open/issues](https://github.com/veralifeos/vera-open/issues).
