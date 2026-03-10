"""FinancialResearchPack — SEC filings, earnings, crypto, financial news."""

import logging

from vera.research.base import ResearchItem, ResearchPack, ResearchResult
from vera.research.packs.financial.sources import (
    CoinGeckoSource,
    DeFiLlamaSource,
    EdgarSource,
    FinancialNewsSource,
    FinnhubSource,
)
from vera.research.scoring import ScoringEngine, create_embedder

logger = logging.getLogger(__name__)

FINANCIAL_DISCLAIMER = "This is not financial advice. Always do your own research."


class FinancialResearchPack(ResearchPack):
    """Monitor SEC filings, earnings, crypto, and financial news."""

    name = "financial"
    description = "Monitor SEC filings, earnings, crypto, and financial news"

    def __init__(self):
        self._embedder = None
        self._embedder_initialized = False

    def _get_scoring_engine(self) -> ScoringEngine:
        if not self._embedder_initialized:
            self._embedder = create_embedder()
            self._embedder_initialized = True
        return ScoringEngine(embedder=self._embedder)

    async def collect(self, config: dict) -> list[ResearchItem]:
        """Coleta de 5 fontes: Finnhub, EDGAR, CoinGecko, DeFiLlama, news RSS."""
        all_items: list[ResearchItem] = []
        sources = [
            FinnhubSource(),
            EdgarSource(),
            CoinGeckoSource(),
            DeFiLlamaSource(),
            FinancialNewsSource(),
        ]

        for source in sources:
            try:
                raw_items = await source.fetch(config)
                for raw in raw_items:
                    item = source.parse(raw)
                    if item:
                        all_items.append(item)
            except Exception as e:
                logger.warning("Financial source '%s' falhou: %s", source.name, e)

        return all_items

    async def score(self, items: list[ResearchItem], config: dict) -> list[ResearchItem]:
        """Keywords (ticker, company name) + embedding."""
        scoring_cfg = config.get("scoring", {})
        weights_cfg = scoring_cfg.get("weights", {})
        kw_weight = weights_cfg.get("keyword", 0.5)
        emb_weight = weights_cfg.get("embedding", 0.5)

        engine = self._get_scoring_engine()

        # Build keywords from watchlist
        watchlist_stocks = config.get("watchlist", {}).get("stocks", [])
        watchlist_crypto = config.get("watchlist", {}).get("crypto", [])

        keywords = []
        for stock in watchlist_stocks:
            keywords.append(stock.get("ticker", ""))
            keywords.append(stock.get("name", ""))
        for crypto in watchlist_crypto:
            keywords.append(crypto.get("symbol", ""))
            keywords.append(crypto.get("id", ""))
        keywords = [k for k in keywords if k]

        reference = " ".join(keywords)

        for item in items:
            kw_score = engine.score_keywords(item, keywords)
            emb_score = engine.score_embedding(item, reference)
            item.score = engine.score_composite(
                kw_score, emb_score, weights=(kw_weight, emb_weight)
            )

        return items

    def format_for_briefing(self, result: ResearchResult) -> str:
        """Formatado por categoria + DISCLAIMER sempre no final."""
        if not result.items:
            return FINANCIAL_DISCLAIMER

        output = self._format_categories(result)
        return f"{output}\n{FINANCIAL_DISCLAIMER}"

    def _format_categories(self, result: ResearchResult) -> str:
        """Formata items agrupados por categoria."""
        if result.synthesis:
            return result.synthesis

        categories: dict[str, list[ResearchItem]] = {}
        for item in result.items:
            cat = item.metadata.get("category", "other")
            categories.setdefault(cat, []).append(item)

        parts = []
        for cat_name, items in categories.items():
            items.sort(key=lambda x: x.score, reverse=True)
            display_name = {
                "earnings": "Earnings",
                "sec_filing": "SEC Filings",
                "crypto": "Crypto",
                "defi": "DeFi",
                "news": "Financial News",
            }.get(cat_name, cat_name.title())

            top = items[:3]
            summaries = [i.title[:60] for i in top]
            parts.append(f"{display_name} ({len(items)}): {'; '.join(summaries)}")

        return "\n".join(parts)
