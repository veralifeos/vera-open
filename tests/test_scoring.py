"""Testes para ScoringEngine."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from vera.research.base import ResearchItem
from vera.research.scoring import ScoringEngine, _cosine_similarity


def _make_item(title="Test", content="Test content", **kwargs):
    return ResearchItem(
        id="test-id",
        title=title,
        url="https://example.com",
        source_name="Test",
        published=None,
        content=content,
        **kwargs,
    )


def _engine_with_embedder():
    mock = MagicMock()
    mock.encode.return_value = [[1, 0], [1, 0]]
    return ScoringEngine(embedder=mock)


class TestScoreKeywords:
    def test_exact_match(self):
        engine = ScoringEngine()
        item = _make_item(title="AI regulation in Europe")
        score = engine.score_keywords(item, ["AI regulation"])
        assert score > 0.0

    def test_partial_match(self):
        engine = ScoringEngine()
        item = _make_item(title="AI regulation", content="Policy changes in EU")
        score = engine.score_keywords(item, ["AI regulation", "climate change"])
        assert 0.0 < score < 1.0

    def test_no_match(self):
        engine = ScoringEngine()
        item = _make_item(title="Sports news", content="Football match results")
        score = engine.score_keywords(item, ["quantum computing"])
        assert score == 0.0

    def test_empty_keywords(self):
        engine = ScoringEngine()
        item = _make_item()
        assert engine.score_keywords(item, []) == 0.0

    def test_weighted_keywords(self):
        engine = ScoringEngine()
        item = _make_item(title="AI regulation policy")
        weights = {"AI regulation": 2.0, "climate": 1.0}
        score = engine.score_keywords(item, list(weights.keys()), weights)
        assert score > 0.0

    def test_case_insensitive(self):
        engine = ScoringEngine()
        item = _make_item(title="ai REGULATION Policy")
        score = engine.score_keywords(item, ["AI Regulation"])
        assert score > 0.0


class TestScoreEmbedding:
    def test_without_embedder(self):
        """Sem embedder retorna 0.0 (ignorado no composite)."""
        engine = ScoringEngine(embedder=None)
        item = _make_item()
        assert engine.score_embedding(item, "reference text") == 0.0

    def test_with_mock_embedder(self):
        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = [
            [1.0, 0.0, 0.0],  # item embedding
            [0.9, 0.1, 0.0],  # reference embedding
        ]
        engine = ScoringEngine(embedder=mock_embedder)
        item = _make_item()
        score = engine.score_embedding(item, "reference")
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Similar vectors should score high


class TestScoreComposite:
    def test_without_embedder_uses_keyword_only(self):
        """Sem embedder, score composto = keyword score direto."""
        engine = ScoringEngine()
        assert not engine.has_embedder
        assert engine.score_composite(0.8, 0.0) == 0.8
        assert engine.score_composite(0.3, 0.0) == 0.3

    def test_with_embedder_uses_weights(self):
        """Com embedder, aplica pesos normalmente."""
        engine = _engine_with_embedder()
        assert engine.has_embedder
        score = engine.score_composite(0.8, 0.6)
        expected = 0.4 * 0.8 + 0.6 * 0.6
        assert abs(score - expected) < 0.001

    def test_with_embedder_custom_weights(self):
        engine = _engine_with_embedder()
        score = engine.score_composite(0.8, 0.6, weights=(0.7, 0.3))
        expected = 0.7 * 0.8 + 0.3 * 0.6
        assert abs(score - expected) < 0.001


class TestScoreLLM:
    @pytest.mark.asyncio
    async def test_llm_scoring_success(self):
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "0.75"

        engine = ScoringEngine()
        item = _make_item()
        score = await engine.score_llm(item, "AI jobs", mock_llm)
        assert score == 0.75

    @pytest.mark.asyncio
    async def test_llm_scoring_failure(self):
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = Exception("API error")

        engine = ScoringEngine()
        item = _make_item()
        score = await engine.score_llm(item, "AI jobs", mock_llm)
        assert score == 0.5  # Fallback


class TestCosineSimilarity:
    def test_identical(self):
        assert abs(_cosine_similarity([1, 0], [1, 0]) - 1.0) < 0.001

    def test_orthogonal(self):
        assert abs(_cosine_similarity([1, 0], [0, 1])) < 0.001

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0], [1, 1]) == 0.0
