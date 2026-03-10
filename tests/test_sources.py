"""Testes para RSSSource e APISource."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.research.sources.api import APISource, _extract_json_path
from vera.research.sources.rss import RSSSource, _compute_item_id

# ─── RSSSource ─────────────────────────────────────────────────────────────


class TestRSSSource:
    def test_name(self):
        source = RSSSource("https://example.com/feed", "TestFeed")
        assert source.name == "TestFeed"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        source = RSSSource("https://example.com/feed", "Test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Test Article</title>
              <link>https://example.com/article1</link>
              <description>Test desc</description>
            </item>
          </channel>
        </rss>"""
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("vera.research.sources.rss.httpx.AsyncClient", return_value=mock_client):
            with patch("vera.research.sources.rss._load_rss_cache", return_value={}):
                with patch("vera.research.sources.rss._save_rss_cache"):
                    entries = await source.fetch({})

        assert len(entries) == 1
        assert entries[0]["title"] == "Test Article"

    @pytest.mark.asyncio
    async def test_fetch_304_not_modified(self):
        source = RSSSource("https://example.com/feed", "Test")

        mock_response = MagicMock()
        mock_response.status_code = 304
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("vera.research.sources.rss.httpx.AsyncClient", return_value=mock_client):
            with patch("vera.research.sources.rss._load_rss_cache", return_value={}):
                entries = await source.fetch({})

        assert entries == []

    def test_parse_valid_entry(self):
        source = RSSSource("https://example.com/feed", "TestFeed")
        entry = {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "This is a test article summary.",
            "published_parsed": (2026, 3, 10, 8, 0, 0, 0, 69, 0),
        }
        item = source.parse(entry)
        assert item is not None
        assert item.title == "Test Article"
        assert item.url == "https://example.com/article"
        assert item.source_name == "TestFeed"
        assert item.content == "This is a test article summary."
        assert item.published is not None

    def test_parse_missing_title(self):
        source = RSSSource("https://example.com/feed", "Test")
        item = source.parse({"link": "https://example.com"})
        assert item is None

    def test_parse_missing_link(self):
        source = RSSSource("https://example.com/feed", "Test")
        item = source.parse({"title": "Test"})
        assert item is None

    def test_parse_content_fallback(self):
        source = RSSSource("https://example.com/feed", "Test")
        # Uses description when no summary
        item = source.parse(
            {
                "title": "Test",
                "link": "https://example.com",
                "description": "Desc content",
            }
        )
        assert item is not None
        assert item.content == "Desc content"

    def test_parse_content_truncation(self):
        source = RSSSource("https://example.com/feed", "Test")
        item = source.parse(
            {
                "title": "Test",
                "link": "https://example.com",
                "summary": "x" * 3000,
            }
        )
        assert item is not None
        assert len(item.content) == 2000


class TestComputeItemId:
    def test_deterministic(self):
        id1 = _compute_item_id("Title", "https://url.com", "Source")
        id2 = _compute_item_id("Title", "https://url.com", "Source")
        assert id1 == id2

    def test_case_insensitive_title(self):
        id1 = _compute_item_id("Title", "https://url.com", "Source")
        id2 = _compute_item_id("title", "https://url.com", "Source")
        assert id1 == id2


# ─── APISource ─────────────────────────────────────────────────────────────


class TestAPISource:
    def test_name(self):
        source = APISource("https://api.example.com", "TestAPI")
        assert source.name == "TestAPI"

    @pytest.mark.asyncio
    async def test_fetch_simple(self):
        source = APISource(
            "https://api.example.com/data",
            "TestAPI",
            json_path="results",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"title": "Item 1"}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("vera.research.sources.api.httpx.AsyncClient", return_value=mock_client):
            items = await source.fetch({})

        assert len(items) == 1
        assert items[0]["title"] == "Item 1"

    @pytest.mark.asyncio
    async def test_fetch_paginated(self):
        source = APISource(
            "https://api.example.com/data",
            "TestAPI",
            json_path="items",
            pagination={
                "type": "offset",
                "param": "offset",
                "limit_param": "limit",
                "limit": 2,
                "max_pages": 2,
            },
        )

        page1_resp = MagicMock()
        page1_resp.json.return_value = {"items": [{"title": "A"}, {"title": "B"}]}
        page1_resp.raise_for_status = MagicMock()

        page2_resp = MagicMock()
        page2_resp.json.return_value = {"items": [{"title": "C"}]}
        page2_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[page1_resp, page2_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("vera.research.sources.api.httpx.AsyncClient", return_value=mock_client):
            items = await source.fetch({})

        assert len(items) == 3

    def test_parse_generic(self):
        source = APISource("https://api.example.com", "TestAPI")
        item = source.parse(
            {
                "title": "Test Item",
                "url": "https://example.com/item",
                "description": "A test description",
            }
        )
        assert item is not None
        assert item.title == "Test Item"
        assert item.url == "https://example.com/item"

    def test_parse_missing_title(self):
        source = APISource("https://api.example.com", "TestAPI")
        item = source.parse({"url": "https://example.com"})
        assert item is None


class TestExtractJsonPath:
    def test_none_path_list(self):
        assert _extract_json_path([1, 2, 3], None) == [1, 2, 3]

    def test_none_path_dict(self):
        assert _extract_json_path({"a": 1}, None) == [{"a": 1}]

    def test_simple_path(self):
        data = {"results": [1, 2]}
        assert _extract_json_path(data, "results") == [1, 2]

    def test_nested_path(self):
        data = {"data": {"items": [1, 2, 3]}}
        assert _extract_json_path(data, "data.items") == [1, 2, 3]

    def test_missing_path(self):
        assert _extract_json_path({"a": 1}, "b.c") == []
