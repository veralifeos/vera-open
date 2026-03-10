"""Testes para ResearchItem, ResearchResult, ResearchPack ABC."""

from datetime import datetime, timezone

import pytest

from vera.research.base import ResearchItem, ResearchPack, ResearchResult


class TestResearchItem:
    def test_create_minimal(self):
        item = ResearchItem(
            id="abc123",
            title="Test Article",
            url="https://example.com/article",
            source_name="TestSource",
            published=None,
            content="Some content here",
        )
        assert item.id == "abc123"
        assert item.title == "Test Article"
        assert item.score == 0.0
        assert item.metadata == {}
        assert item.topic is None

    def test_create_full(self):
        now = datetime.now(timezone.utc)
        item = ResearchItem(
            id="def456",
            title="Full Article",
            url="https://example.com/full",
            source_name="FullSource",
            published=now,
            content="Detailed content",
            score=0.85,
            metadata={"author": "Test"},
            topic="AI",
        )
        assert item.score == 0.85
        assert item.metadata["author"] == "Test"
        assert item.topic == "AI"
        assert item.published == now

    def test_default_metadata_independent(self):
        """Ensure default_factory creates independent dicts."""
        item1 = ResearchItem(id="1", title="A", url="", source_name="", published=None, content="")
        item2 = ResearchItem(id="2", title="B", url="", source_name="", published=None, content="")
        item1.metadata["key"] = "value"
        assert "key" not in item2.metadata


class TestResearchResult:
    def test_create(self):
        now = datetime.now(timezone.utc)
        result = ResearchResult(
            pack_name="news",
            items=[],
            new_count=0,
            total_checked=10,
            sources_checked=3,
            sources_failed=["BadSource"],
            timestamp=now,
        )
        assert result.pack_name == "news"
        assert result.new_count == 0
        assert result.total_checked == 10
        assert result.sources_failed == ["BadSource"]
        assert result.synthesis == ""

    def test_with_synthesis(self):
        result = ResearchResult(
            pack_name="test",
            items=[],
            new_count=0,
            total_checked=0,
            sources_checked=0,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
            synthesis="Test synthesis text",
        )
        assert result.synthesis == "Test synthesis text"


class TestResearchPackABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            ResearchPack()

    def test_concrete_implementation(self):
        class MockPack(ResearchPack):
            @property
            def name(self):
                return "mock"

            @property
            def description(self):
                return "Mock pack"

            async def collect(self, config):
                return []

            async def score(self, items, config):
                return items

            def format_for_briefing(self, result):
                return ""

        pack = MockPack()
        assert pack.name == "mock"
        assert pack.description == "Mock pack"
        assert pack.get_default_config() == {}

    def test_get_default_config_overridable(self):
        class CustomPack(ResearchPack):
            @property
            def name(self):
                return "custom"

            @property
            def description(self):
                return "Custom"

            async def collect(self, config):
                return []

            async def score(self, items, config):
                return items

            def format_for_briefing(self, result):
                return ""

            def get_default_config(self):
                return {"threshold": 0.7}

        pack = CustomPack()
        assert pack.get_default_config() == {"threshold": 0.7}
