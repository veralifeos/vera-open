"""JobScorer — scoring hibrido 3 camadas para vagas."""

import logging
import re

from vera.research.base import ResearchItem
from vera.research.scoring import ScoringEngine

logger = logging.getLogger(__name__)


class JobScorer:
    """Scoring hibrido 3 camadas: rules -> embedding -> LLM."""

    def __init__(self, scoring_engine: ScoringEngine):
        self._engine = scoring_engine

    def score_rules(self, item: ResearchItem, criteria: dict) -> float:
        """Camada 1: rule-based, 10 dimensoes. Retorna 0.0-1.0."""
        scores: list[float] = []
        text = f"{item.title} {item.content}".lower()
        meta = item.metadata

        # 1. Keywords match
        keywords = criteria.get("keywords", [])
        if keywords:
            matched = sum(1 for kw in keywords if kw.lower() in text)
            scores.append(min(matched / max(len(keywords), 1), 1.0))

        # 2. Location
        location_pref = criteria.get("location", "").lower()
        if location_pref:
            item_location = meta.get("location", "").lower()
            if location_pref in item_location or location_pref == "remote":
                if "remote" in text or "remote" in item_location:
                    scores.append(1.0)
                elif location_pref in item_location:
                    scores.append(0.8)
                else:
                    scores.append(0.3)
            else:
                scores.append(0.2)

        # 3. Seniority
        seniority_prefs = [s.lower() for s in criteria.get("seniority", [])]
        if seniority_prefs:
            matched = any(s in text for s in seniority_prefs)
            scores.append(1.0 if matched else 0.3)

        # 4. Salary range
        salary_min = criteria.get("salary_min", 0)
        if salary_min:
            salary_str = meta.get("salary", "")
            salary_nums = re.findall(r"[\d,]+", str(salary_str))
            if salary_nums:
                try:
                    max_salary = max(int(n.replace(",", "")) for n in salary_nums)
                    scores.append(1.0 if max_salary >= salary_min else 0.4)
                except ValueError:
                    scores.append(0.5)
            else:
                scores.append(0.5)  # No salary info = neutral

        # 5. Stack match
        stack = [s.lower() for s in criteria.get("stack", [])]
        if stack:
            matched = sum(1 for s in stack if s in text)
            scores.append(min(matched / max(len(stack), 1) * 2, 1.0))

        # 6. Exclude keywords
        exclude = [e.lower() for e in criteria.get("exclude_keywords", [])]
        if exclude:
            has_exclude = any(e in text for e in exclude)
            scores.append(0.0 if has_exclude else 1.0)

        # 7. Remote policy
        if "remote" in text or meta.get("remote"):
            scores.append(1.0)
        else:
            scores.append(0.5)

        if not scores:
            return 0.5

        return sum(scores) / len(scores)

    def score_embedding(self, item: ResearchItem, cv_text: str) -> float:
        """Camada 2: similaridade CV <-> job description."""
        return self._engine.score_embedding(item, cv_text)

    async def score_llm(self, item: ResearchItem, profile: str, llm) -> float:
        """Camada 3: Haiku avalia fit qualitativo."""
        return await self._engine.score_llm(item, profile, llm)

    def composite(
        self,
        rule_score: float,
        embed_score: float,
        llm_score: float | None = None,
        weights: tuple[float, float, float] = (0.40, 0.35, 0.25),
    ) -> float:
        """Score composto. Redistribui pesos de camadas ausentes."""
        w_rule, w_embed, w_llm = weights

        # Sem embedder: redistribui peso do embedding para rules
        if not self._engine.has_embedder:
            w_embed = 0.0

        if llm_score is None:
            w_llm = 0.0

        total = w_rule + w_embed + w_llm
        if total == 0:
            return rule_score
        # Normaliza pesos para somar 1.0
        w_rule /= total
        w_embed /= total
        w_llm /= total

        return w_rule * rule_score + w_embed * embed_score + w_llm * (llm_score or 0.0)
