"""ScoringEngine — keywords + embeddings + LLM opcional."""

import logging
import math
import re

from vera.research.base import ResearchItem

logger = logging.getLogger(__name__)

_EMBEDDER_WARNING_LOGGED = False


class ScoringEngine:
    """Motor de scoring multi-camada para Research Packs."""

    def __init__(self, embedder=None):
        """
        Args:
            embedder: Instancia de sentence-transformers SentenceTransformer ou
                      light-embed TextEmbedding. Se None, scoring so usa keywords.
        """
        global _EMBEDDER_WARNING_LOGGED
        self._embedder = embedder
        self._encode_fn = _resolve_encode_fn(embedder)
        if self._encode_fn is None and not _EMBEDDER_WARNING_LOGGED:
            logger.warning(
                "Embedder não disponível, usando keyword-only scoring. "
                "Instale sentence-transformers para scoring semântico."
            )
            _EMBEDDER_WARNING_LOGGED = True

    @property
    def has_embedder(self) -> bool:
        """True se embedder está disponível."""
        return self._encode_fn is not None

    def score_keywords(
        self,
        item: ResearchItem,
        keywords: list[str],
        weights: dict | None = None,
    ) -> float:
        """Camada 1: keyword matching com proporção de cobertura.

        Score = cobertura (fração de keywords matchados) × intensidade média.
        1 de 3 keywords match = ~0.33, 3 de 3 = ~1.0.
        Retorna 0.0-1.0.
        """
        if not keywords:
            return 0.0

        text = f"{item.title} {item.content}".lower()
        weights = weights or {}
        total_weight = 0.0
        matched_weight = 0.0
        matched_count = 0

        for kw in keywords:
            kw_lower = kw.lower()
            w = weights.get(kw, 1.0)
            total_weight += w

            # Conta ocorrencias (case-insensitive)
            pattern = re.escape(kw_lower)
            matches = len(re.findall(pattern, text))
            if matches > 0:
                # TF simples: log(1 + count) normalizado
                tf = math.log1p(matches) / math.log1p(10)  # cap em ~10 matches
                matched_weight += w * min(tf, 1.0)
                matched_count += 1

        if total_weight == 0 or matched_count == 0:
            return 0.0

        # Cobertura: fração de keywords presentes
        coverage = matched_count / len(keywords)
        # Intensidade: TF média dos que matcharam
        matched_kw_weight = sum(
            weights.get(kw, 1.0) for kw in keywords
            if len(re.findall(re.escape(kw.lower()), text)) > 0
        )
        intensity = matched_weight / matched_kw_weight if matched_kw_weight else 0.0
        # Score: sqrt(coverage) evita penalizar listas grandes de keywords
        return min(math.sqrt(coverage) * (0.6 + 0.4 * intensity), 1.0)

    def score_embedding(self, item: ResearchItem, reference_text: str) -> float:
        """Camada 2: similaridade semantica via embeddings.

        Retorna 0.0-1.0. Se embedder nao disponivel, retorna 0.0 (ignorado).
        """
        if self._encode_fn is None:
            return 0.0

        try:
            item_text = f"{item.title}. {item.content[:500]}"
            embeddings = self._encode_fn([item_text, reference_text])

            # Cosine similarity
            sim = _cosine_similarity(embeddings[0], embeddings[1])
            # Normaliza de [-1, 1] para [0, 1]
            return max(0.0, min(1.0, (sim + 1.0) / 2.0))
        except Exception as e:
            logger.warning("Erro no embedding scoring: %s", e)
            return 0.0

    def score_composite(
        self,
        keyword_score: float,
        embedding_score: float,
        weights: tuple[float, float] = (0.4, 0.6),
    ) -> float:
        """Score composto. Sem embedder, rebalanceia para keyword-only."""
        if not self.has_embedder:
            return keyword_score
        w_kw, w_emb = weights
        return w_kw * keyword_score + w_emb * embedding_score

    async def score_llm(
        self,
        item: ResearchItem,
        criteria: str,
        llm_provider,
    ) -> float:
        """Camada 3 (opcional): LLM avalia fit qualitativo.

        Retorna 0.0-1.0. Default OFF — so usar para packs que precisam.
        """
        prompt = (
            f"Rate the relevance of this item to the criteria on a scale of 0.0 to 1.0.\n\n"
            f"Criteria: {criteria}\n\n"
            f"Title: {item.title}\n"
            f"Content: {item.content[:500]}\n\n"
            f"Respond with ONLY a number between 0.0 and 1.0."
        )

        try:
            response = await llm_provider.generate(
                system_prompt="You are a relevance scoring assistant. Respond with only a number.",
                user_prompt=prompt,
                max_tokens=10,
                temperature=0.0,
            )
            score = float(response.strip())
            return max(0.0, min(1.0, score))
        except (ValueError, TypeError, Exception) as e:
            logger.warning("LLM scoring falhou: %s", e)
            return 0.5


def _resolve_encode_fn(embedder):
    """Resolve funcao de encode do embedder (sentence-transformers ou light-embed)."""
    if embedder is None:
        return None
    # sentence-transformers: .encode()
    if hasattr(embedder, "encode"):
        return embedder.encode
    # light-embed: .encode() tambem
    return None


def _cosine_similarity(a, b) -> float:
    """Cosine similarity entre dois vetores."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def create_embedder():
    """Tenta criar embedder. Retorna None se nenhum disponivel.

    Ordem: sentence-transformers > light-embed > None.
    """
    # Tenta sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedder: sentence-transformers (all-MiniLM-L6-v2)")
        return model
    except ImportError:
        pass

    # Tenta light-embed
    try:
        from light_embed import TextEmbedding

        model = TextEmbedding("all-MiniLM-L6-v2")
        logger.info("Embedder: light-embed (all-MiniLM-L6-v2)")
        return model
    except ImportError:
        pass

    return None
