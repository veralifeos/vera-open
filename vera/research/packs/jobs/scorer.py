"""JobScorer — scoring hibrido 3 camadas para vagas.

Rule-based scorer:
  - Se candidate_profile.yaml existe (uso pessoal), aplica 14 dimensoes:
    3-tier title matching (exact/close/adjacent), target_companies,
    B2B SaaS, stack 2+, remote, CLT/USD, CLT explicito, Brasil location,
    PT-BR posting, beneficios, setor preferido, easy apply, pipeline
    pequeno, referral, CRO keywords. Soma cap em 10, normalizada 0-1.
  - Senao (uso generico do open), cai no scorer 7-dim por criteria
    vindo do config/packs/jobs.yaml.
"""

import logging
import re

from vera.research.base import ResearchItem
from vera.research.packs.jobs.profile import load_profile, load_target_companies
from vera.research.scoring import ScoringEngine

logger = logging.getLogger(__name__)


# Bonus CRO — aplicado quando nao ha title_exact mas o texto tem keywords CRO
_CRO_KEYWORDS = (
    "conversion rate", "conversion optimization", "conversion funnel",
    "a/b test", "ab test", "experimentation", "landing page optimization",
    "otimizacao de conversao", "otimização de conversão",
    "taxa de conversao", "taxa de conversão",
    "funil de conversao", "funil de conversão",
    "performance marketing", "performance digital",
    "cro ",
)

_B2B_SIGNALS = ("b2b saas", "enterprise software", "enterprise platform")

_CLT_SIGNALS = ("clt", "carteira assinada", "regime clt")

_BRASIL_SIGNALS = (
    "brasil", "brazil", "remoto brasil", "belo horizonte",
    "sao paulo", "são paulo", "rio de janeiro", "curitiba",
    "porto alegre", "florianopolis", "florianópolis",
)

_PTBR_SIGNALS = (
    "vaga", "requisitos", "beneficios", "benefícios",
    "experiencia", "experiência",
)

_BENEFICIO_SIGNALS = (
    "vale alimentacao", "vale alimentação", "vale refeicao", "vale refeição",
    "plano de saude", "plano de saúde", "gympass", "wellhub", "plr",
)


class JobScorer:
    """Scoring hibrido 3 camadas: rules -> embedding -> LLM."""

    def __init__(self, scoring_engine: ScoringEngine):
        self._engine = scoring_engine

    def score_rules(self, item: ResearchItem, criteria: dict) -> float:
        """Camada 1: rule-based. Retorna 0.0-1.0.

        Usa 14-dim (profile) se disponivel; cai no legacy 7-dim caso contrario.
        """
        profile = load_profile()
        if profile.get("scoring_weights") and profile.get("target_roles"):
            return self._score_rules_14dim(item, profile)
        return self._score_rules_legacy(item, criteria)

    # ------------------------------------------------------------------
    # 14-dim scorer (candidate_profile.yaml — uso pessoal do Fernando)
    # ------------------------------------------------------------------

    def _score_rules_14dim(self, item: ResearchItem, profile: dict) -> float:
        """Rule-based 14 dimensoes, pesos do profile. Retorna 0.0-1.0."""
        weights = profile.get("scoring_weights", {})
        meta = item.metadata or {}

        title = (item.title or "").lower()
        description = (item.content or "").lower()
        text = f"{title} {description}"
        company = (meta.get("company") or "").strip().lower()
        location = (meta.get("location") or "").lower()
        target_companies = load_target_companies()

        score = 0.0

        # 1. Title match 3-tier (mutuamente exclusivos)
        roles = profile.get("target_roles", {})
        exact_roles = [r.lower() for r in roles.get("exact", [])]
        close_roles = [r.lower() for r in roles.get("close", [])]
        adjacent_roles = [r.lower() for r in roles.get("adjacent", [])]

        has_exact = any(r in title for r in exact_roles)
        has_close = not has_exact and any(r in title for r in close_roles)
        has_adjacent = (
            not has_exact
            and not has_close
            and any(r in title for r in adjacent_roles)
        )

        if has_exact:
            score += weights.get("title_exact", 3.0)
        elif has_close:
            score += weights.get("title_close", 2.0)
        elif has_adjacent:
            score += weights.get("title_adjacent", 1.0)

        # 1b. CRO keywords bonus (so se nao exact — evita double-count)
        if not has_exact and any(k in text for k in _CRO_KEYWORDS):
            score += weights.get("cro_keywords", 0.5)

        # 2. B2B SaaS (literal, sinonimos, ou empresa-alvo)
        is_target = bool(company) and company in target_companies
        if is_target or ("b2b" in text and "saas" in text) or any(s in text for s in _B2B_SIGNALS):
            score += weights.get("b2b_saas", 1.5)

        # 3. Stack match (2+ matches em strong stack)
        strong_stack = [s.lower() for s in profile.get("stack", {}).get("strong", [])]
        stack_matches = sum(1 for s in strong_stack if s in text)
        if stack_matches >= 2:
            score += weights.get("stack_match_2plus", 1.0)

        # 4. Remote
        is_remote = bool(meta.get("is_remote") or meta.get("remote"))
        if is_remote or "remote" in location or "remoto" in location:
            score += weights.get("remote", 1.0)

        # 5. CLT ou USD
        salary_currency = (meta.get("salary_currency") or "").lower()
        contract_type = (meta.get("contract_type") or "").lower()
        if salary_currency == "usd" or "clt" in contract_type:
            score += weights.get("clt_or_usd", 0.5)

        # 6. CLT explicito no texto
        if any(s in text for s in _CLT_SIGNALS) or "clt" in contract_type:
            score += weights.get("clt_explicit", 1.0)

        # 7. Brasil location
        if any(s in location for s in _BRASIL_SIGNALS) or any(
            s in text for s in ("bh", "minas gerais")
        ):
            score += weights.get("brasil_location", 0.5)

        # 8. PT-BR posting (2+ sinais)
        if sum(1 for s in _PTBR_SIGNALS if s in text) >= 2:
            score += weights.get("portugues", 0.3)

        # 9. Beneficios mencionados
        if any(s in text for s in _BENEFICIO_SIGNALS) or (
            "va" in text.split() and "vr" in text.split()
        ):
            score += weights.get("beneficios", 0.3)

        # 10. Setor preferido
        sectors = [s.lower() for s in profile.get("sectors_preferred", [])]
        if any(s in text for s in sectors):
            score += weights.get("preferred_sector", 0.5)

        # 11. Easy Apply
        if meta.get("easy_apply"):
            score += weights.get("easy_apply", 0.3)

        # 12. Pipeline pequeno
        applicants = meta.get("applicants")
        if applicants is not None and applicants < 25:
            score += weights.get("small_pipeline", 0.2)

        # 13. Referral
        if meta.get("is_referral"):
            score += weights.get("referral", 0.5)

        # 14. Target company (empresa curada)
        if is_target:
            score += weights.get("target_company", 2.0)

        # Cap em 10 e normaliza para 0-1
        return min(score, 10.0) / 10.0

    # ------------------------------------------------------------------
    # Legacy 7-dim scorer (uso generico do open via config/packs/jobs.yaml)
    # ------------------------------------------------------------------

    def _score_rules_legacy(self, item: ResearchItem, criteria: dict) -> float:
        """Scorer 7-dim original do open, por config/packs/jobs.yaml."""
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
