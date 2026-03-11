"""RSSSource — busca e parseia feeds RSS/Atom via httpx + feedparser."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import mktime

import feedparser
import httpx
from tenacity import retry

from vera.research.base import ResearchItem
from vera.research.retry import RETRY_KWARGS
from vera.research.sources.base import Source

logger = logging.getLogger(__name__)

_RSS_CACHE_PATH = Path("state/rss_cache.json")

_RETRY_KWARGS = RETRY_KWARGS


def _load_rss_cache() -> dict:
    """Carrega cache de ETag/Last-Modified por feed URL."""
    if _RSS_CACHE_PATH.exists():
        try:
            return json.loads(_RSS_CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_rss_cache(cache: dict) -> None:
    """Salva cache de ETag/Last-Modified."""
    _RSS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RSS_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


class RSSSource(Source):
    """Busca feed RSS/Atom via httpx com Conditional GET."""

    def __init__(self, url: str, source_name: str, timeout: float = 30.0):
        self._url = url
        self._source_name = source_name
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._source_name

    @retry(**_RETRY_KWARGS)
    async def fetch(self, config: dict) -> list[dict]:
        """Busca feed RSS. Usa Conditional GET (ETag/If-Modified-Since)."""
        cache = _load_rss_cache()
        feed_cache = cache.get(self._url, {})

        headers = {"User-Agent": "Vera/0.2 (+https://github.com/veralifeos/vera-open)"}
        if feed_cache.get("etag"):
            headers["If-None-Match"] = feed_cache["etag"]
        if feed_cache.get("last_modified"):
            headers["If-Modified-Since"] = feed_cache["last_modified"]

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self._url,
                headers=headers,
                timeout=self._timeout,
                follow_redirects=True,
            )

        # 304 Not Modified — nada mudou
        if resp.status_code == 304:
            logger.debug("RSS %s: 304 Not Modified", self._source_name)
            return []

        resp.raise_for_status()

        # Atualiza cache
        new_cache_entry = {}
        if resp.headers.get("etag"):
            new_cache_entry["etag"] = resp.headers["etag"]
        if resp.headers.get("last-modified"):
            new_cache_entry["last_modified"] = resp.headers["last-modified"]
        if new_cache_entry:
            cache[self._url] = new_cache_entry
            _save_rss_cache(cache)

        # Parse com feedparser
        feed = feedparser.parse(resp.text)
        return feed.get("entries", [])

    def parse(self, raw_item: dict) -> ResearchItem | None:
        """Converte entry do feedparser para ResearchItem."""
        title = raw_item.get("title", "").strip()
        link = raw_item.get("link", "").strip()
        if not title or not link:
            return None

        # Content: tenta summary, content, ou description
        content = ""
        if raw_item.get("summary"):
            content = raw_item["summary"]
        elif raw_item.get("content"):
            content = raw_item["content"][0].get("value", "")
        elif raw_item.get("description"):
            content = raw_item["description"]

        # Published date
        published = None
        if raw_item.get("published_parsed"):
            try:
                published = datetime.fromtimestamp(
                    mktime(raw_item["published_parsed"]), tz=timezone.utc
                )
            except (ValueError, TypeError, OverflowError):
                pass

        item_id = _compute_item_id(title, link, self._source_name)

        return ResearchItem(
            id=item_id,
            title=title,
            url=link,
            source_name=self._source_name,
            published=published,
            content=content[:2000],  # Limita content
        )


def _compute_item_id(title: str, url: str, source: str) -> str:
    """Hash MD5 de titulo normalizado + URL."""
    normalized = f"{title.lower().strip()}|{url.strip()}|{source}"
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()
