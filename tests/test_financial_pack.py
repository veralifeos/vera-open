"""Testes para FinancialResearchPack."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from vera.research.base import ResearchItem, ResearchResult
from vera.research.packs.financial.pack import FINANCIAL_DISCLAIMER, FinancialResearchPack
from vera.research.packs.financial.sources import (
    CoinGeckoSource,
    DeFiLlamaSource,
    EdgarSource,
    FinnhubSource,
)


def _make_item(title="Test", category="news", score=0.0, **meta):
    return ResearchItem(
        id=f"id-{title}",
        title=title,
        url="https://example.com",
        source_name="Test",
        published=None,
        content=f"Content about {title}",
        score=score,
        metadata={"category": category, **meta},
    )


_SAMPLE_CONFIG = {
    "api_keys": {
        "finnhub_env": "FINNHUB_API_KEY",
        "coingecko_env": "COINGECKO_API_KEY",
    },
    "edgar": {"user_agent": "Test test@test.com"},
    "watchlist": {
        "stocks": [
            {"ticker": "AAPL", "name": "Apple", "cik": "0000320193"},
        ],
        "crypto": [
            {"id": "bitcoin", "symbol": "BTC"},
        ],
    },
    "categories": {
        "sec_filings": {"enabled": True, "filing_types": ["10-K"]},
        "earnings": {"enabled": True},
        "crypto": {"enabled": True, "price_change_threshold": 5.0},
        "news": {"enabled": True, "sources": []},
    },
    "scoring": {"weights": {"keyword": 0.5, "embedding": 0.5}},
}


# ─── Source parse tests ───────────────────────────────────────────────────


class TestFinnhubSource:
    def test_parse_earnings(self):
        source = FinnhubSource()
        item = source.parse(
            {
                "_type": "earnings",
                "symbol": "AAPL",
                "date": "2026-04-15",
                "epsEstimate": 1.5,
                "quarter": 2,
            }
        )
        assert item is not None
        assert "AAPL" in item.title
        assert "Earnings" in item.title
        assert item.metadata["category"] == "earnings"

    def test_parse_news(self):
        source = FinnhubSource()
        item = source.parse(
            {
                "_type": "news",
                "_ticker": "AAPL",
                "headline": "Apple reports record earnings",
                "url": "https://example.com/news",
                "summary": "Apple beat expectations",
                "source": "Reuters",
            }
        )
        assert item is not None
        assert "Apple" in item.title
        assert item.metadata["category"] == "news"

    def test_parse_missing_symbol(self):
        source = FinnhubSource()
        assert source.parse({"_type": "earnings"}) is None

    def test_parse_unknown_type(self):
        source = FinnhubSource()
        assert source.parse({"_type": "unknown"}) is None

    @pytest.mark.asyncio
    async def test_fetch_no_key(self):
        """Sem key retorna lista vazia."""
        source = FinnhubSource()
        with patch.dict("os.environ", {}, clear=True):
            items = await source.fetch({"api_keys": {"finnhub_env": "MISSING_KEY"}})
        assert items == []


class TestEdgarSource:
    def test_parse_filing(self):
        source = EdgarSource()
        item = source.parse(
            {
                "form": "10-K",
                "ticker": "AAPL",
                "company": "Apple",
                "date": "2026-01-15",
                "description": "Annual report",
                "url": "https://sec.gov/filing/123",
            }
        )
        assert item is not None
        assert "SEC 10-K" in item.title
        assert "Apple" in item.title
        assert item.metadata["category"] == "sec_filing"

    def test_parse_missing_form(self):
        source = EdgarSource()
        assert source.parse({"ticker": "AAPL"}) is None

    @pytest.mark.asyncio
    async def test_fetch_no_watchlist(self):
        source = EdgarSource()
        items = await source.fetch({"watchlist": {"stocks": []}})
        assert items == []


class TestCoinGeckoSource:
    def test_parse_crypto(self):
        source = CoinGeckoSource()
        item = source.parse(
            {
                "_type": "crypto",
                "symbol": "BTC",
                "price": 95000.50,
                "change_24h": 3.2,
            }
        )
        assert item is not None
        assert "BTC" in item.title
        assert "$95,000.50" in item.title
        assert item.metadata["category"] == "crypto"

    def test_parse_negative_change(self):
        source = CoinGeckoSource()
        item = source.parse(
            {
                "_type": "crypto",
                "symbol": "ETH",
                "price": 3500.0,
                "change_24h": -5.1,
            }
        )
        assert item is not None
        assert "-5.1%" in item.title

    @pytest.mark.asyncio
    async def test_fetch_disabled(self):
        source = CoinGeckoSource()
        items = await source.fetch(
            {
                "categories": {"crypto": {"enabled": False}},
            }
        )
        assert items == []


class TestDeFiLlamaSource:
    def test_parse_protocol(self):
        source = DeFiLlamaSource()
        item = source.parse(
            {
                "_type": "defi",
                "name": "Aave",
                "tvl": 15_000_000_000,
                "change_1d": 2.5,
                "url": "https://defillama.com/protocol/aave",
            }
        )
        assert item is not None
        assert "Aave" in item.title
        assert "15.0B" in item.title
        assert item.metadata["category"] == "defi"

    @pytest.mark.asyncio
    async def test_fetch_disabled(self):
        source = DeFiLlamaSource()
        items = await source.fetch(
            {
                "categories": {"crypto": {"enabled": False}},
            }
        )
        assert items == []


# ─── Pack tests ────────────────────────────────────────────────────────────


class TestFinancialPack:
    def test_name(self):
        pack = FinancialResearchPack()
        assert pack.name == "financial"

    @pytest.mark.asyncio
    async def test_collect_source_failure_continues(self):
        """Uma fonte falhando nao impede as outras."""
        pack = FinancialResearchPack()

        # Mock all sources to fail
        with patch(
            "vera.research.packs.financial.pack.FinnhubSource.fetch",
            side_effect=Exception("API error"),
        ):
            with patch(
                "vera.research.packs.financial.pack.EdgarSource.fetch",
                side_effect=Exception("Import error"),
            ):
                with patch(
                    "vera.research.packs.financial.pack.CoinGeckoSource.fetch",
                    side_effect=Exception("Rate limit"),
                ):
                    with patch(
                        "vera.research.packs.financial.pack.DeFiLlamaSource.fetch",
                        side_effect=Exception("Timeout"),
                    ):
                        with patch(
                            "vera.research.packs.financial.pack.FinancialNewsSource.fetch",
                            side_effect=Exception("RSS error"),
                        ):
                            items = await pack.collect(_SAMPLE_CONFIG)
        assert items == []

    @pytest.mark.asyncio
    async def test_score_assigns_scores(self):
        pack = FinancialResearchPack()
        items = [_make_item("Apple AAPL earnings beat", category="earnings")]
        scored = await pack.score(items, _SAMPLE_CONFIG)
        assert scored[0].score > 0.0

    def test_disclaimer_always_present_with_items(self):
        pack = FinancialResearchPack()
        items = [_make_item("AAPL News", category="news", score=0.8)]
        result = ResearchResult(
            pack_name="financial",
            items=items,
            new_count=1,
            total_checked=5,
            sources_checked=3,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        formatted = pack.format_for_briefing(result)
        assert FINANCIAL_DISCLAIMER in formatted

    def test_disclaimer_present_even_empty(self):
        pack = FinancialResearchPack()
        result = ResearchResult(
            pack_name="financial",
            items=[],
            new_count=0,
            total_checked=0,
            sources_checked=0,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        formatted = pack.format_for_briefing(result)
        assert formatted == FINANCIAL_DISCLAIMER

    def test_format_grouped_by_category(self):
        pack = FinancialResearchPack()
        items = [
            _make_item("AAPL 10-K", category="sec_filing", score=0.9),
            _make_item("BTC $95K", category="crypto", score=0.8),
            _make_item("Market rally", category="news", score=0.7),
        ]
        result = ResearchResult(
            pack_name="financial",
            items=items,
            new_count=3,
            total_checked=10,
            sources_checked=5,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        formatted = pack.format_for_briefing(result)
        assert "SEC Filings" in formatted
        assert "Crypto" in formatted
        assert "Financial News" in formatted
        assert FINANCIAL_DISCLAIMER in formatted

    def test_format_with_synthesis(self):
        pack = FinancialResearchPack()
        items = [_make_item("Test", score=0.8)]
        result = ResearchResult(
            pack_name="financial",
            items=items,
            new_count=1,
            total_checked=1,
            sources_checked=1,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
            synthesis="Markets rallied on AI optimism.",
        )
        formatted = pack.format_for_briefing(result)
        assert "Markets rallied" in formatted
        assert FINANCIAL_DISCLAIMER in formatted


class TestFinancialPackBYOK:
    @pytest.mark.asyncio
    async def test_finnhub_missing_key(self):
        """Key ausente desabilita fonte silenciosamente."""
        source = FinnhubSource()
        with patch.dict("os.environ", {}, clear=True):
            items = await source.fetch({"api_keys": {"finnhub_env": "MISSING"}})
        assert items == []

    @pytest.mark.asyncio
    async def test_coingecko_disabled_category(self):
        source = CoinGeckoSource()
        items = await source.fetch(
            {
                "categories": {"crypto": {"enabled": False}},
            }
        )
        assert items == []


class TestFinancialPackRegistry:
    def test_registered(self):
        from vera.research.registry import registry

        registry.discover()
        assert "financial" in registry.list_available()
