"""APISource — busca generica de REST APIs via httpx."""

import asyncio
import hashlib
import logging
from datetime import datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from vera.research.base import ResearchItem
from vera.research.sources.base import Source

logger = logging.getLogger(__name__)

_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=2, min=2, max=8),
    "retry": retry_if_exception_type((httpx.HTTPError, TimeoutError)),
    "reraise": True,
}


class APISource(Source):
    """GET generico via httpx com rate limiting e paginacao."""

    def __init__(
        self,
        base_url: str,
        source_name: str,
        headers: dict | None = None,
        json_path: str | None = None,
        timeout: float = 30.0,
        rate_limit_delay: float = 0.0,
        pagination: dict | None = None,
    ):
        """
        Args:
            base_url: URL base do endpoint.
            source_name: Nome legivel da fonte.
            headers: Headers HTTP customizados.
            json_path: Dot-path para extrair items do JSON (ex: "data.items").
            timeout: Timeout em segundos.
            rate_limit_delay: Delay em segundos entre requests (rate limiting).
            pagination: Config de paginacao {type: "offset"|"page"|"cursor",
                        param: str, limit_param: str, limit: int, max_pages: int}.
        """
        self._base_url = base_url
        self._source_name = source_name
        self._headers = headers or {}
        self._json_path = json_path
        self._timeout = timeout
        self._rate_limit_delay = rate_limit_delay
        self._pagination = pagination

    @property
    def name(self) -> str:
        return self._source_name

    @retry(**_RETRY_KWARGS)
    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> dict:
        """Busca uma pagina da API."""
        resp = await client.get(
            url,
            headers=self._headers,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()

    async def fetch(self, config: dict) -> list[dict]:
        """Busca items da API com paginacao opcional."""
        all_items: list[dict] = []

        async with httpx.AsyncClient() as client:
            if not self._pagination:
                # Single request
                data = await self._fetch_page(client, self._base_url)
                items = _extract_json_path(data, self._json_path)
                all_items.extend(items if isinstance(items, list) else [])
            else:
                # Paginated
                pag = self._pagination
                max_pages = pag.get("max_pages", 3)
                pag_type = pag.get("type", "offset")
                param = pag.get("param", "offset")
                limit_param = pag.get("limit_param", "limit")
                limit = pag.get("limit", 20)

                for page_num in range(max_pages):
                    separator = "&" if "?" in self._base_url else "?"

                    if pag_type == "offset":
                        offset = page_num * limit
                        url = f"{self._base_url}{separator}{param}={offset}&{limit_param}={limit}"
                    elif pag_type == "page":
                        url = (
                            f"{self._base_url}{separator}"
                            f"{param}={page_num + 1}&{limit_param}={limit}"
                        )
                    else:
                        url = self._base_url

                    data = await self._fetch_page(client, url)
                    items = _extract_json_path(data, self._json_path)
                    if not items or not isinstance(items, list):
                        break
                    all_items.extend(items)

                    if len(items) < limit:
                        break  # Ultima pagina

                    if self._rate_limit_delay > 0 and page_num < max_pages - 1:
                        await asyncio.sleep(self._rate_limit_delay)

        return all_items

    def parse(self, raw_item: dict) -> ResearchItem | None:
        """Parse generico — subclasses devem sobrescrever para parsing especifico."""
        title = raw_item.get("title", "").strip()
        url = raw_item.get("url", raw_item.get("link", "")).strip()
        if not title:
            return None

        content = raw_item.get("description", raw_item.get("content", ""))
        if isinstance(content, list):
            content = content[0] if content else ""
        content = str(content)[:2000]

        published = None
        date_str = raw_item.get("published", raw_item.get("date", raw_item.get("created_at")))
        if date_str and isinstance(date_str, str):
            try:
                published = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        item_id = hashlib.md5(
            f"{title.lower().strip()}|{url}|{self._source_name}".encode()
        ).hexdigest()

        return ResearchItem(
            id=item_id,
            title=title,
            url=url or "",
            source_name=self._source_name,
            published=published,
            content=content,
        )


def _extract_json_path(data: dict | list, path: str | None) -> list | dict:
    """Extrai valor de um JSON usando dot-path (ex: 'data.items')."""
    if path is None:
        return data if isinstance(data, list) else [data]

    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            current = current.get(key, [])
        else:
            return []
    return current if isinstance(current, list) else [current]
