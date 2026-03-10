"""Testes para PackRegistry."""

from vera.research.base import ResearchPack
from vera.research.registry import PackRegistry


class MockPack(ResearchPack):
    name = "mock"
    description = "Mock pack for testing"

    async def collect(self, config):
        return []

    async def score(self, items, config):
        return items

    def format_for_briefing(self, result):
        return ""


class AnotherPack(ResearchPack):
    name = "another"
    description = "Another mock"

    async def collect(self, config):
        return []

    async def score(self, items, config):
        return items

    def format_for_briefing(self, result):
        return ""


class TestPackRegistry:
    def test_register_and_get(self):
        reg = PackRegistry()
        reg.register(MockPack)
        assert reg.get("mock") == MockPack

    def test_get_unknown(self):
        reg = PackRegistry()
        assert reg.get("nonexistent") is None

    def test_list_available(self):
        reg = PackRegistry()
        reg.register(MockPack)
        reg.register(AnotherPack)
        available = reg.list_available()
        assert "mock" in available
        assert "another" in available

    def test_list_empty(self):
        reg = PackRegistry()
        assert reg.list_available() == []

    def test_discover_no_crash(self):
        """Discover should not crash even if no packs are available."""
        reg = PackRegistry()
        reg.discover()  # Should not raise
