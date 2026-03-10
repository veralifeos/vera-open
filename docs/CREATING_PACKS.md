# Creating Research Packs

This guide walks you through creating a custom Research Pack for Vera.

## Architecture

A Research Pack is a self-contained module that implements the `ResearchPack` ABC:

```
vera/research/packs/your_pack/
├── __init__.py    # Register the pack
├── pack.py        # ResearchPack implementation
├── sources.py     # Custom sources (optional)
└── pack.yaml      # Default config (optional)
```

## Step 1: Implement ResearchPack

```python
# vera/research/packs/academic/pack.py
from vera.research.base import ResearchItem, ResearchPack, ResearchResult
from vera.research.sources.rss import RSSSource
from vera.research.scoring import ScoringEngine, create_embedder


class AcademicPack(ResearchPack):
    name = "academic"
    description = "Monitor academic papers from arXiv and other sources"

    async def collect(self, config: dict) -> list[ResearchItem]:
        """Collect papers from configured sources."""
        items = []
        for source_cfg in config.get("sources", []):
            source = RSSSource(source_cfg["url"], source_cfg["name"])
            entries = await source.fetch(config)
            for entry in entries:
                item = source.parse(entry)
                if item:
                    items.append(item)
        return items

    async def score(self, items: list[ResearchItem], config: dict) -> list[ResearchItem]:
        """Score papers by keyword relevance."""
        engine = ScoringEngine(embedder=create_embedder())
        keywords = config.get("keywords", [])
        for item in items:
            item.score = engine.score_keywords(item, keywords)
        return items

    def format_for_briefing(self, result: ResearchResult) -> str:
        """Format for the daily briefing."""
        if not result.items:
            return ""
        top = sorted(result.items, key=lambda x: x.score, reverse=True)[:5]
        lines = [f"Academic ({len(result.items)} new):"]
        for item in top:
            lines.append(f"  - {item.title[:80]}")
        return "\n".join(lines)
```

## Step 2: Register the Pack

```python
# vera/research/packs/academic/__init__.py
from vera.research.packs.academic.pack import AcademicPack
from vera.research.registry import registry

registry.register(AcademicPack)
```

## Step 3: Create Config

```yaml
# config/packs/academic.yaml
pack:
  name: "academic"
  display_name: "Academic Papers"

sources:
  - url: "https://export.arxiv.org/rss/cs.AI"
    name: "arXiv CS.AI"
  - url: "https://export.arxiv.org/rss/cs.LG"
    name: "arXiv CS.LG"

keywords: ["transformer", "LLM", "reinforcement learning"]

scoring:
  relevance_threshold: 0.4

dedup:
  ttl_days: 14
```

## Step 4: Write Tests

```python
# tests/test_academic_pack.py
import pytest
from vera.research.packs.academic.pack import AcademicPack

class TestAcademicPack:
    def test_name(self):
        assert AcademicPack().name == "academic"

    @pytest.mark.asyncio
    async def test_collect_empty(self):
        pack = AcademicPack()
        items = await pack.collect({"sources": []})
        assert items == []
```

## Available Building Blocks

| Component | Use for |
|---|---|
| `RSSSource` | Any RSS/Atom feed (conditional GET built-in) |
| `APISource` | REST APIs with pagination and rate limiting |
| `ScoringEngine` | Keyword matching, embedding similarity, LLM scoring |
| `DedupEngine` | TTL-based deduplication with JSON persistence |
| `SynthesisEngine` | LLM summarization by topic |

## Conventions

- Pack names are lowercase, no spaces: `academic`, `social_media`, `weather`
- Packs are self-contained: deleting a pack directory breaks nothing
- Use `httpx` for HTTP (not `aiohttp`)
- Missing API keys = silently disable the source, never crash
- All tests must be mockable with zero external calls

## Contributing

1. Create your pack in `vera/research/packs/your_pack/`
2. Add tests in `tests/test_your_pack.py`
3. Add example config in `config/packs/your_pack.example.yaml`
4. Submit a PR (see [CONTRIBUTING.md](../CONTRIBUTING.md))
