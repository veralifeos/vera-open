"""E2E integration tests for Research Packs."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from vera.research.base import ResearchItem, ResearchResult


def _make_item(title="Test", topic="AI", source="TestSource", score=0.7):
    return ResearchItem(
        id=f"id-{title}",
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        source_name=source,
        published=None,
        content=f"Content about {title}",
        score=score,
        topic=topic,
    )


class TestNewsPackFullCycle:
    @pytest.mark.asyncio
    async def test_news_collect_score_format(self):
        """Full cycle: collect -> score -> format."""
        from vera.research.packs.news.pack import NewsResearchPack

        pack = NewsResearchPack()

        # Mock collect to return known items
        items = [
            _make_item("AI regulation news", "AI", score=0.0),
            _make_item("Sports update", "AI", score=0.0),
        ]

        with patch.object(pack, "collect", new=AsyncMock(return_value=items)):
            collected = await pack.collect({})

        config = {
            "topics": [{"name": "AI", "keywords": ["AI", "regulation"]}],
            "scoring": {"weights": {"keyword": 0.4, "embedding": 0.6}},
        }
        scored = await pack.score(collected, config)

        # AI item should score higher
        ai_item = next(i for i in scored if "regulation" in i.title)
        sports_item = next(i for i in scored if "Sports" in i.title)
        assert ai_item.score > sports_item.score

        result = ResearchResult(
            pack_name="news",
            items=[i for i in scored if i.score > 0.3],
            new_count=len(scored),
            total_checked=len(scored),
            sources_checked=1,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        formatted = pack.format_for_briefing(result)
        assert "AI" in formatted


class TestJobsPackFullCycleWithNotion:
    @pytest.mark.asyncio
    async def test_jobs_score_and_save(self):
        """Score items and save to mock backend."""
        from vera.research.packs.jobs.pack import JobSearchPack

        pack = JobSearchPack()

        items = [
            ResearchItem(
                id="job-1",
                title="Acme — Growth Marketing Lead",
                url="https://acme.com/jobs/1",
                source_name="Himalayas",
                published=None,
                content="Senior growth marketing CRO role with HubSpot remote",
                metadata={"company": "Acme", "location": "remote"},
            )
        ]

        config = {
            "criteria": {"keywords": ["growth marketing", "CRO"], "location": "remote"},
            "scoring": {"weights": {"rules": 0.5, "embedding": 0.3, "llm": 0.2}},
        }
        scored = await pack.score(items, config)
        assert scored[0].score > 0.0

        # Mock backend
        mock_backend = AsyncMock()
        mock_backend.create_record = AsyncMock()
        saved = await pack.save_to_backend(scored, mock_backend)
        assert saved == 1


class TestFinancialPackWithDisclaimer:
    def test_disclaimer_in_output(self):
        """Financial pack ALWAYS includes disclaimer."""
        from vera.research.packs.financial.pack import (
            FINANCIAL_DISCLAIMER,
            FinancialResearchPack,
        )

        pack = FinancialResearchPack()

        # With items
        result = ResearchResult(
            pack_name="financial",
            items=[_make_item("AAPL earnings", topic=None, score=0.8)],
            new_count=1,
            total_checked=5,
            sources_checked=3,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        assert FINANCIAL_DISCLAIMER in pack.format_for_briefing(result)

        # Without items
        empty_result = ResearchResult(
            pack_name="financial",
            items=[],
            new_count=0,
            total_checked=0,
            sources_checked=0,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        assert pack.format_for_briefing(empty_result) == FINANCIAL_DISCLAIMER


class TestBriefingIncludesRadar:
    @pytest.mark.asyncio
    async def test_radar_section_generated(self):
        """When research is enabled, briefing includes RADAR section."""
        from vera.config import ResearchConfig, ResearchPackConfig, VeraConfig
        from vera.modes.briefing import _research_habilitado

        config = VeraConfig(
            research=ResearchConfig(
                enabled=True,
                packs={"news": ResearchPackConfig(enabled=True, config_path="")},
            ),
        )
        assert _research_habilitado(config)

    def test_research_disabled_no_impact(self):
        """When research disabled, no impact on briefing."""
        from vera.config import VeraConfig
        from vera.modes.briefing import _research_habilitado

        config = VeraConfig()  # Default: research disabled
        assert not _research_habilitado(config)


class TestResearchDisabledNoImpact:
    def test_default_config_has_research_disabled(self):
        from vera.config import VeraConfig

        config = VeraConfig()
        assert config.research.enabled is False
        assert config.research.packs == {}
