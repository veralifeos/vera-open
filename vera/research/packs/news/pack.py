"""NewsResearchPack — monitoramento de noticias e topicos via RSS."""

import logging

from vera.research.base import ResearchItem, ResearchPack, ResearchResult
from vera.research.scoring import ScoringEngine, create_embedder
from vera.research.sources.rss import RSSSource

logger = logging.getLogger(__name__)


class NewsResearchPack(ResearchPack):
    """Monitor news and topics from multiple RSS sources."""

    name = "news"
    description = "Monitor news and topics from RSS feeds"

    def __init__(self):
        self._embedder = None
        self._embedder_initialized = False

    def _get_scoring_engine(self) -> ScoringEngine:
        """Lazy init do embedder."""
        if not self._embedder_initialized:
            self._embedder = create_embedder()
            self._embedder_initialized = True
        return ScoringEngine(embedder=self._embedder)

    async def collect(self, config: dict) -> list[ResearchItem]:
        """Para cada topico em config['topics'], busca todos os feeds RSS."""
        topics = config.get("topics", [])
        if not topics:
            return []

        all_items: list[ResearchItem] = []

        for topic_cfg in topics:
            topic_name = topic_cfg.get("name", "Unnamed")
            sources = topic_cfg.get("sources", [])

            for source_cfg in sources:
                if source_cfg.get("type") != "rss":
                    continue

                url = source_cfg.get("url", "")
                name = source_cfg.get("name", url)

                if not url:
                    continue

                try:
                    source = RSSSource(url, name)
                    entries = await source.fetch(config)

                    for entry in entries:
                        item = source.parse(entry)
                        if item:
                            item.topic = topic_name
                            all_items.append(item)

                except Exception as e:
                    logger.warning("News pack: erro na fonte '%s': %s", name, e)

        return all_items

    async def score(self, items: list[ResearchItem], config: dict) -> list[ResearchItem]:
        """Keywords do topico + embedding similarity."""
        topics_cfg = {t["name"]: t for t in config.get("topics", [])}
        scoring_cfg = config.get("scoring", {})
        weights_cfg = scoring_cfg.get("weights", {})
        kw_weight = weights_cfg.get("keyword", 0.4)
        emb_weight = weights_cfg.get("embedding", 0.6)

        engine = self._get_scoring_engine()

        for item in items:
            topic_cfg = topics_cfg.get(item.topic or "", {})
            keywords = topic_cfg.get("keywords", [])

            # Keyword score
            kw_score = engine.score_keywords(item, keywords)

            # Embedding score (reference = keywords joined)
            reference = " ".join(keywords) if keywords else item.topic or ""
            emb_score = engine.score_embedding(item, reference)

            # Composite
            item.score = engine.score_composite(
                kw_score, emb_score, weights=(kw_weight, emb_weight)
            )

        return items

    def format_for_briefing(self, result: ResearchResult) -> str:
        """'{topic} ({n} novos): titulos'

        Omitir topicos sem itens novos.
        """
        if not result.items:
            return ""

        # Agrupa por topico
        topics: dict[str, list[ResearchItem]] = {}
        for item in result.items:
            t = item.topic or "Geral"
            topics.setdefault(t, []).append(item)

        lines = []
        for topic_name, items in topics.items():
            # Ordena por score desc
            items.sort(key=lambda x: x.score, reverse=True)
            top_titles = [i.title[:60] for i in items[:3]]
            titles_str = "; ".join(top_titles)
            lines.append(f"{topic_name} ({len(items)} novos): {titles_str}")

        if result.synthesis:
            return result.synthesis

        return "\n".join(lines)
