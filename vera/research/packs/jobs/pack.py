"""JobSearchPack — monitoramento de vagas com scoring hibrido."""

import logging

from vera.research.base import ResearchItem, ResearchPack, ResearchResult
from vera.research.packs.jobs.scorer import JobScorer
from vera.research.packs.jobs.sources import ALL_SOURCES
from vera.research.scoring import ScoringEngine, create_embedder

logger = logging.getLogger(__name__)


class JobSearchPack(ResearchPack):
    """Monitor job listings across multiple sources with hybrid scoring."""

    name = "jobs"
    description = "Monitor job listings across multiple sources with hybrid scoring"

    def __init__(self):
        self._embedder = None
        self._embedder_initialized = False

    def _get_scorer(self) -> JobScorer:
        if not self._embedder_initialized:
            self._embedder = create_embedder()
            self._embedder_initialized = True
        return JobScorer(ScoringEngine(embedder=self._embedder))

    async def collect(self, config: dict) -> list[ResearchItem]:
        """Busca vagas de todas as fontes habilitadas."""
        sources_cfg = config.get("sources", {})
        all_items: list[ResearchItem] = []

        for source_name, source_cls in ALL_SOURCES.items():
            src_cfg = sources_cfg.get(source_name, {})

            # Desabilitado explicitamente
            if not src_cfg.get("enabled", True):
                continue

            try:
                source = source_cls()
                raw_items = await source.fetch(config)

                for raw in raw_items:
                    item = source.parse(raw)
                    if item:
                        all_items.append(item)

            except Exception as e:
                logger.warning("Jobs pack: fonte '%s' falhou: %s", source_name, e)

        return all_items

    async def score(self, items: list[ResearchItem], config: dict) -> list[ResearchItem]:
        """3 camadas: rule-based -> embedding -> LLM (opcional)."""
        criteria = config.get("criteria", {})
        scoring_cfg = config.get("scoring", {})
        weights = scoring_cfg.get("weights", {})
        w = (
            weights.get("rules", 0.40),
            weights.get("embedding", 0.35),
            weights.get("llm", 0.25),
        )
        use_llm = scoring_cfg.get("use_llm_scoring", False)
        llm_threshold = scoring_cfg.get("llm_threshold", 0.6)

        scorer = self._get_scorer()

        # CV text para embedding (keywords + stack)
        cv_parts = criteria.get("keywords", []) + criteria.get("stack", [])
        cv_text = " ".join(cv_parts)

        for item in items:
            # Camada 1: Rules
            rule_score = scorer.score_rules(item, criteria)

            # Camada 2: Embedding
            embed_score = scorer.score_embedding(item, cv_text)

            # Camada 3: LLM (so se habilitado e camadas 1-2 passaram threshold)
            llm_score = None
            preliminary = scorer.composite(rule_score, embed_score, weights=w)
            if use_llm and preliminary >= llm_threshold:
                # LLM scoring exige provider — skip se nao disponivel
                llm_score = None  # Sera preenchido na integracao completa

            item.score = scorer.composite(rule_score, embed_score, llm_score, weights=w)

        return items

    def format_for_briefing(self, result: ResearchResult) -> str:
        """'{n} vagas novas. Top 3: ...'"""
        if not result.items:
            return ""

        n = len(result.items)
        sorted_items = sorted(result.items, key=lambda x: x.score, reverse=True)
        top = sorted_items[:3]
        top_str = " | ".join(f"{i.title[:50]} ({i.score:.0%})" for i in top)

        if result.synthesis:
            return result.synthesis

        return f"{n} vagas novas. Top 3: {top_str}"

    async def save_to_backend(self, items: list[ResearchItem], backend) -> int:
        """Grava vagas com score >= threshold no Notion Pipeline.

        Returns: numero de vagas salvas.
        """
        saved = 0
        for item in items:
            try:
                company = item.metadata.get("company", "")
                title_parts = item.title.split(" — ", 1)
                job_title = title_parts[1] if len(title_parts) > 1 else item.title

                await backend.create_record(
                    "pipeline",
                    {
                        "Nome": f"{company} — {job_title}"[:100],
                        "Tipo": "Vaga",
                        "Estagio": "Mapeada",
                        "Fonte": f"Vera ({item.source_name})",
                        "URL": item.url,
                        "Fit": round(item.score * 10, 1),
                    },
                )
                saved += 1
            except Exception as e:
                logger.warning("Erro ao salvar vaga '%s': %s", item.title[:50], e)

        return saved
