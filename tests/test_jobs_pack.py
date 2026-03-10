"""Testes para JobSearchPack — fontes, scorer, pack."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from vera.research.base import ResearchItem, ResearchResult
from vera.research.packs.jobs.pack import JobSearchPack
from vera.research.packs.jobs.scorer import JobScorer
from vera.research.packs.jobs.sources import (
    ALL_SOURCES,
    ArbeitnowSource,
    GreenhouseSource,
    HimalayasSource,
    LeverSource,
    RemoteOKSource,
    RemotiveSource,
)
from vera.research.scoring import ScoringEngine


def _make_item(title="Test Job", company="TestCo", score=0.0, **meta):
    return ResearchItem(
        id=f"id-{title}",
        title=f"{company} — {title}",
        url="https://example.com/job",
        source_name="Test",
        published=None,
        content=f"Job description for {title} at {company}. Remote. Senior.",
        score=score,
        metadata={"company": company, "location": "remote", **meta},
    )


_CRITERIA = {
    "keywords": ["growth marketing", "CRO"],
    "location": "remote",
    "seniority": ["senior", "lead"],
    "salary_min": 10000,
    "stack": ["HubSpot", "GA4"],
    "exclude_keywords": ["intern", "junior"],
}

_SAMPLE_CONFIG = {
    "criteria": _CRITERIA,
    "sources": {
        "himalayas": {"enabled": True},
        "remotive": {"enabled": True},
        "remoteok": {"enabled": False},
    },
    "scoring": {
        "weights": {"rules": 0.40, "embedding": 0.35, "llm": 0.25},
        "use_llm_scoring": False,
        "relevance_threshold": 0.5,
    },
}


# ─── Source tests ──────────────────────────────────────────────────────────


class TestSources:
    def test_all_sources_registered(self):
        assert len(ALL_SOURCES) == 9
        expected = {
            "himalayas",
            "remotive",
            "remoteok",
            "arbeitnow",
            "jooble",
            "jsearch",
            "greenhouse",
            "lever",
            "ashby",
        }
        assert set(ALL_SOURCES.keys()) == expected

    def test_himalayas_parse(self):
        source = HimalayasSource()
        item = source.parse(
            {
                "title": "Growth Manager",
                "companyName": "Acme",
                "applicationUrl": "https://acme.com/apply",
                "description": "Looking for a growth manager",
                "location": "Remote",
            }
        )
        assert item is not None
        assert "Acme" in item.title
        assert "Growth Manager" in item.title

    def test_remotive_parse(self):
        source = RemotiveSource()
        item = source.parse(
            {
                "title": "CRO Specialist",
                "company_name": "BigCorp",
                "url": "https://remotive.com/job/123",
                "description": "CRO role",
            }
        )
        assert item is not None
        assert "BigCorp" in item.title

    def test_remoteok_parse(self):
        source = RemoteOKSource()
        item = source.parse(
            {
                "position": "Marketing Lead",
                "company": "StartupX",
                "url": "https://remoteok.com/jobs/123",
                "description": "Lead marketing",
            }
        )
        assert item is not None
        assert "StartupX" in item.title

    def test_arbeitnow_parse(self):
        source = ArbeitnowSource()
        item = source.parse(
            {
                "title": "Product Manager",
                "company_name": "EuroCorp",
                "url": "https://arbeitnow.com/job/123",
                "description": "PM role",
                "remote": True,
            }
        )
        assert item is not None
        assert item.metadata.get("remote") is True

    def test_parse_missing_title_returns_none(self):
        source = HimalayasSource()
        assert source.parse({"companyName": "Acme"}) is None

    def test_greenhouse_parse(self):
        source = GreenhouseSource()
        item = source.parse(
            {
                "title": "Engineer",
                "_board": "stripe",
                "absolute_url": "https://boards.greenhouse.io/stripe/123",
                "content": "Engineering role",
                "location": {"name": "San Francisco, CA"},
            }
        )
        assert item is not None
        assert "stripe" in item.title.lower()

    def test_lever_parse(self):
        source = LeverSource()
        item = source.parse(
            {
                "text": "Designer",
                "categories": {"team": "Design", "location": "NYC"},
                "hostedUrl": "https://lever.co/jobs/123",
                "descriptionPlain": "Design role",
            }
        )
        assert item is not None
        assert "Designer" in item.title


# ─── Scorer tests ──────────────────────────────────────────────────────────


class TestJobScorer:
    def test_score_rules_keyword_match(self):
        scorer = JobScorer(ScoringEngine())
        item = _make_item("Growth Marketing Lead")
        item.content = "Growth marketing CRO role with HubSpot and GA4. Senior."
        score = scorer.score_rules(item, _CRITERIA)
        assert score > 0.5

    def test_score_rules_exclude_keyword(self):
        scorer = JobScorer(ScoringEngine())
        item = _make_item("Junior Growth Intern")
        item.content = "Junior intern position for growth marketing"
        score = scorer.score_rules(item, _CRITERIA)
        # Should be penalized by exclude keywords
        item2 = _make_item("Senior Growth Lead")
        item2.content = "Senior growth marketing lead with CRO"
        score2 = scorer.score_rules(item2, _CRITERIA)
        assert score < score2

    def test_score_rules_empty_criteria(self):
        scorer = JobScorer(ScoringEngine())
        item = _make_item()
        score = scorer.score_rules(item, {})
        # With empty criteria, only remote dimension fires (item has "remote")
        assert 0.0 <= score <= 1.0

    def test_composite_without_llm(self):
        scorer = JobScorer(ScoringEngine())
        score = scorer.composite(0.8, 0.6, llm_score=None)
        # Should redistribute weights: 0.40/(0.40+0.35)=0.533, 0.35/(0.40+0.35)=0.467
        expected = (0.40 / 0.75) * 0.8 + (0.35 / 0.75) * 0.6
        assert abs(score - expected) < 0.01

    def test_composite_with_llm(self):
        scorer = JobScorer(ScoringEngine())
        score = scorer.composite(0.8, 0.6, 0.9)
        expected = 0.40 * 0.8 + 0.35 * 0.6 + 0.25 * 0.9
        assert abs(score - expected) < 0.01

    def test_score_rules_remote_boost(self):
        scorer = JobScorer(ScoringEngine())
        item = _make_item("Role")
        item.content = "Remote position worldwide"
        item.metadata["remote"] = True
        score = scorer.score_rules(item, {"location": "remote"})
        assert score > 0.5


# ─── Pack tests ────────────────────────────────────────────────────────────


class TestJobSearchPack:
    def test_name_and_description(self):
        pack = JobSearchPack()
        assert pack.name == "jobs"
        assert "job" in pack.description.lower()

    @pytest.mark.asyncio
    async def test_collect_respects_enabled(self):
        """Fontes desabilitadas sao puladas."""
        pack = JobSearchPack()

        with patch.object(
            pack,
            "collect",
            new=AsyncMock(return_value=[_make_item("Job A"), _make_item("Job B")]),
        ):
            items = await pack.collect(_SAMPLE_CONFIG)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_collect_source_offline(self):
        """Fonte offline nao crasheia o pack."""
        pack = JobSearchPack()

        # Desabilita todas as fontes exceto himalayas e remotive
        config = {
            "sources": {
                "himalayas": {"enabled": True},
                "remotive": {"enabled": True},
                "remoteok": {"enabled": False},
                "arbeitnow": {"enabled": False},
                "jooble": {"enabled": False},
                "jsearch": {"enabled": False},
                "greenhouse": {"enabled": False},
                "lever": {"enabled": False},
                "ashby": {"enabled": False},
            },
            "criteria": {},
        }

        with patch(
            "vera.research.packs.jobs.sources.HimalayasSource.fetch",
            side_effect=ConnectionError("offline"),
        ):
            with patch(
                "vera.research.packs.jobs.sources.RemotiveSource.fetch",
                side_effect=ConnectionError("offline"),
            ):
                items = await pack.collect(config)
        assert items == []

    @pytest.mark.asyncio
    async def test_score_assigns_scores(self):
        pack = JobSearchPack()
        items = [_make_item("Growth Marketing CRO Senior")]
        items[0].content = "Growth marketing CRO senior role with HubSpot GA4 remote"
        scored = await pack.score(items, _SAMPLE_CONFIG)
        assert scored[0].score > 0.0

    def test_format_empty(self):
        pack = JobSearchPack()
        result = ResearchResult(
            pack_name="jobs",
            items=[],
            new_count=0,
            total_checked=0,
            sources_checked=0,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        assert pack.format_for_briefing(result) == ""

    def test_format_with_items(self):
        pack = JobSearchPack()
        items = [
            _make_item("Job A", score=0.9),
            _make_item("Job B", score=0.7),
        ]
        result = ResearchResult(
            pack_name="jobs",
            items=items,
            new_count=2,
            total_checked=10,
            sources_checked=3,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        formatted = pack.format_for_briefing(result)
        assert "2 vagas novas" in formatted
        assert "Top 3" in formatted

    def test_format_with_synthesis(self):
        pack = JobSearchPack()
        items = [_make_item("Job", score=0.8)]
        result = ResearchResult(
            pack_name="jobs",
            items=items,
            new_count=1,
            total_checked=5,
            sources_checked=2,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
            synthesis="3 vagas relevantes encontradas.",
        )
        assert pack.format_for_briefing(result) == "3 vagas relevantes encontradas."


class TestJobPackRegistry:
    def test_registered(self):
        from vera.research.registry import registry

        registry.discover()
        assert "jobs" in registry.list_available()


class TestJobPackSaveToBackend:
    @pytest.mark.asyncio
    async def test_save_calls_backend(self):
        pack = JobSearchPack()
        mock_backend = AsyncMock()
        mock_backend.create_record = AsyncMock()

        items = [_make_item("Growth Lead", "Acme", score=0.85)]
        saved = await pack.save_to_backend(items, mock_backend)

        assert saved == 1
        mock_backend.create_record.assert_called_once()
        call_args = mock_backend.create_record.call_args
        assert call_args[0][0] == "pipeline"
        assert "Acme" in call_args[0][1]["Nome"]

    @pytest.mark.asyncio
    async def test_save_backend_error_continues(self):
        pack = JobSearchPack()
        mock_backend = AsyncMock()
        mock_backend.create_record = AsyncMock(side_effect=Exception("API error"))

        items = [_make_item("Job A"), _make_item("Job B")]
        saved = await pack.save_to_backend(items, mock_backend)
        assert saved == 0  # Both failed but no crash
