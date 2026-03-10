"""Testes para SynthesisEngine."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from vera.research.base import ResearchItem, ResearchResult
from vera.research.synthesis import SynthesisEngine


def _make_item(title="Test", topic=None):
    return ResearchItem(
        id="test-id",
        title=title,
        url="https://example.com",
        source_name="Test",
        published=None,
        content=f"Content about {title}",
        topic=topic,
    )


class TestSynthesizeTopicBase:
    @pytest.mark.asyncio
    async def test_empty_items(self):
        mock_llm = AsyncMock()
        engine = SynthesisEngine(mock_llm)
        result = await engine.synthesize_topic("AI", [])
        assert result == ""
        mock_llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_success(self):
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "AI regulation is evolving rapidly."

        engine = SynthesisEngine(mock_llm)
        items = [_make_item("AI Act passed"), _make_item("New AI rules")]
        result = await engine.synthesize_topic("AI Regulation", items)

        assert result == "AI regulation is evolving rapidly."
        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = Exception("API error")

        engine = SynthesisEngine(mock_llm)
        items = [_make_item("Article One"), _make_item("Article Two")]
        result = await engine.synthesize_topic("Tech", items)

        # Fallback: lista de titulos
        assert "Tech" in result
        assert "Article One" in result

    @pytest.mark.asyncio
    async def test_max_words_in_prompt(self):
        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "Summary."

        engine = SynthesisEngine(mock_llm)
        items = [_make_item("Test")]
        await engine.synthesize_topic("Topic", items, max_words=50)

        call_args = mock_llm.generate.call_args
        assert "50 palavras" in call_args.kwargs["user_prompt"]


class TestSynthesizePack:
    @pytest.mark.asyncio
    async def test_empty_topics(self):
        mock_llm = AsyncMock()
        engine = SynthesisEngine(mock_llm)
        result_obj = ResearchResult(
            pack_name="test",
            items=[],
            new_count=0,
            total_checked=0,
            sources_checked=0,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        result = await engine.synthesize_pack(result_obj, {})
        assert result == ""

    @pytest.mark.asyncio
    async def test_multiple_topics(self):
        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = ["AI summary.", "Crypto summary."]

        engine = SynthesisEngine(mock_llm)
        topics = {
            "AI": [_make_item("AI News")],
            "Crypto": [_make_item("BTC Update")],
        }
        result_obj = ResearchResult(
            pack_name="test",
            items=[],
            new_count=0,
            total_checked=0,
            sources_checked=0,
            sources_failed=[],
            timestamp=datetime.now(timezone.utc),
        )
        result = await engine.synthesize_pack(result_obj, topics)

        assert "AI" in result
        assert "Crypto" in result
        assert mock_llm.generate.call_count == 2
