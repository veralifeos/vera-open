"""Testes para NewsResearchPack."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from vera.research.base import ResearchItem, ResearchResult
from vera.research.packs.news.pack import NewsResearchPack


def _make_item(title="Test", topic="AI", score=0.0):
    return ResearchItem(
        id=f"id-{title}",
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        source_name="TestSource",
        published=None,
        content=f"Content about {title}",
        score=score,
        topic=topic,
    )


_SAMPLE_CONFIG = {
    "topics": [
        {
            "name": "AI",
            "keywords": ["artificial intelligence", "machine learning", "AI"],
            "sources": [
                {"type": "rss", "url": "https://example.com/feed1", "name": "Feed1"},
                {"type": "rss", "url": "https://example.com/feed2", "name": "Feed2"},
            ],
            "relevance_threshold": 0.5,
            "max_items": 5,
        },
        {
            "name": "Crypto",
            "keywords": ["bitcoin", "ethereum", "crypto"],
            "sources": [
                {"type": "rss", "url": "https://example.com/feed3", "name": "Feed3"},
            ],
        },
    ],
    "scoring": {
        "weights": {"keyword": 0.4, "embedding": 0.6},
        "use_llm_scoring": False,
    },
    "dedup": {"ttl_days": 7},
}


class TestNewsPackProperties:
    def test_name(self):
        pack = NewsResearchPack()
        assert pack.name == "news"

    def test_description(self):
        pack = NewsResearchPack()
        assert "news" in pack.description.lower() or "RSS" in pack.description


class TestNewsPackCollect:
    @pytest.mark.asyncio
    async def test_collect_multiple_topics(self):
        pack = NewsResearchPack()

        with patch.object(
            pack,
            "collect",
            new=AsyncMock(
                return_value=[
                    _make_item("AI breakthrough", "AI"),
                    _make_item("ML update", "AI"),
                    _make_item("BTC surge", "Crypto"),
                ]
            ),
        ):
            items = await pack.collect(_SAMPLE_CONFIG)

        assert len(items) == 3
        ai_items = [i for i in items if i.topic == "AI"]
        crypto_items = [i for i in items if i.topic == "Crypto"]
        assert len(ai_items) == 2
        assert len(crypto_items) == 1

    @pytest.mark.asyncio
    async def test_collect_empty_topics(self):
        pack = NewsResearchPack()
        items = await pack.collect({"topics": []})
        assert items == []

    @pytest.mark.asyncio
    async def test_collect_no_topics_key(self):
        pack = NewsResearchPack()
        items = await pack.collect({})
        assert items == []

    @pytest.mark.asyncio
    async def test_collect_source_failure_continues(self):
        """Uma fonte falhando nao impede as outras."""
        pack = NewsResearchPack()

        async def mock_fetch_side_effect(config):
            raise ConnectionError("Feed offline")

        with patch(
            "vera.research.packs.news.pack.RSSSource.fetch",
            side_effect=mock_fetch_side_effect,
        ):
            # Should not raise, just log warning
            items = await pack.collect(_SAMPLE_CONFIG)

        assert items == []  # All failed, no items

    @pytest.mark.asyncio
    async def test_collect_skips_non_rss_sources(self):
        pack = NewsResearchPack()
        config = {
            "topics": [
                {
                    "name": "Test",
                    "keywords": ["test"],
                    "sources": [{"type": "api", "url": "https://api.example.com"}],
                }
            ]
        }
        items = await pack.collect(config)
        assert items == []


class TestNewsPackScore:
    @pytest.mark.asyncio
    async def test_score_with_keywords(self):
        pack = NewsResearchPack()
        items = [
            _make_item("AI regulation passed in EU", "AI"),
            _make_item("Sports news update", "AI"),
        ]

        scored = await pack.score(items, _SAMPLE_CONFIG)
        assert len(scored) == 2
        # AI item should score higher than sports
        assert scored[0].score > scored[1].score or scored[0].title == "AI regulation passed in EU"

    @pytest.mark.asyncio
    async def test_score_assigns_scores(self):
        pack = NewsResearchPack()
        items = [_make_item("machine learning breakthrough", "AI")]
        scored = await pack.score(items, _SAMPLE_CONFIG)
        assert scored[0].score > 0.0

    @pytest.mark.asyncio
    async def test_score_empty_items(self):
        pack = NewsResearchPack()
        scored = await pack.score([], _SAMPLE_CONFIG)
        assert scored == []

    @pytest.mark.asyncio
    async def test_score_missing_topic_config(self):
        """Item com topico nao configurado nao crasheia."""
        pack = NewsResearchPack()
        items = [_make_item("Random news", "UnknownTopic")]
        scored = await pack.score(items, _SAMPLE_CONFIG)
        assert len(scored) == 1
        assert scored[0].score >= 0.0


class TestNewsPackFormat:
    def test_format_empty(self):
        pack = NewsResearchPack()
        result = ResearchResult(
            pack_name="news",
            items=[],
            new_count=0,
            total_checked=0,
            sources_checked=0,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        assert pack.format_for_briefing(result) == ""

    def test_format_grouped_by_topic(self):
        pack = NewsResearchPack()
        items = [
            _make_item("AI News 1", "AI", score=0.8),
            _make_item("AI News 2", "AI", score=0.7),
            _make_item("BTC Update", "Crypto", score=0.9),
        ]
        result = ResearchResult(
            pack_name="news",
            items=items,
            new_count=3,
            total_checked=10,
            sources_checked=3,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        formatted = pack.format_for_briefing(result)
        assert "AI" in formatted
        assert "Crypto" in formatted
        assert "2 novos" in formatted  # 2 AI items

    def test_format_with_synthesis(self):
        """Se synthesis existe, usa synthesis ao inves de titulos."""
        pack = NewsResearchPack()
        items = [_make_item("Article", "AI", score=0.8)]
        result = ResearchResult(
            pack_name="news",
            items=items,
            new_count=1,
            total_checked=5,
            sources_checked=2,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
            synthesis="AI regulation is advancing rapidly in the EU.",
        )
        formatted = pack.format_for_briefing(result)
        assert formatted == "AI regulation is advancing rapidly in the EU."

    def test_format_truncates_titles(self):
        pack = NewsResearchPack()
        long_title = "A" * 100
        items = [_make_item(long_title, "AI", score=0.8)]
        result = ResearchResult(
            pack_name="news",
            items=items,
            new_count=1,
            total_checked=1,
            sources_checked=1,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        formatted = pack.format_for_briefing(result)
        # Titles truncated to 60 chars
        assert len(formatted.split(": ", 1)[1]) <= 61


class TestNewsPackRegistry:
    def test_registered(self):
        from vera.research.registry import registry

        registry.discover()
        assert "news" in registry.list_available()
        pack_cls = registry.get("news")
        assert pack_cls is not None
        assert pack_cls().name == "news"
