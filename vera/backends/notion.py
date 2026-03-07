"""NotionBackend — primeira implementação de StorageBackend.

Usa aiohttp com aiolimiter (3 req/s) + retry tenacity.
Adaptado de vera pessoal (notion_client.py), generalizado.
"""

import asyncio
import logging
import os

import aiohttp
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from vera.backends.base import StorageBackend

logger = logging.getLogger(__name__)

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

# Retry: 3 tentativas, backoff 2s → 4s → 8s
_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=2, min=2, max=30),
    "retry": retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    "reraise": True,
}


class NotionBackend(StorageBackend):
    """Backend Notion com paginação, rate limit e retry."""

    def __init__(self, token: str | None = None, token_env: str = "NOTION_TOKEN"):
        self._token = token or os.environ.get(token_env, "")
        if not self._token:
            raise ValueError(
                f"Token Notion não encontrado. Defina a env var '{token_env}' "
                "ou passe o token diretamente."
            )
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_API_VERSION,
        }
        # Notion API: máximo 3 req/s
        self._limiter = AsyncLimiter(max_rate=3, time_period=1)

    @retry(**_RETRY_KWARGS)
    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        payload: dict | None = None,
    ) -> dict:
        """Faz request com rate limit e retry."""
        async with self._limiter:
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.request(method, url, json=payload, timeout=timeout) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=f"Notion API erro {resp.status}: {text[:200]}",
                    )
                return await resp.json()

    async def query(
        self,
        collection_id: str,
        filters: dict | None = None,
        sorts: list | None = None,
        max_pages: int = 1,
    ) -> list[dict]:
        """Busca registros com paginação completa."""
        url = f"{NOTION_BASE_URL}/databases/{collection_id}/query"
        all_results: list[dict] = []
        start_cursor = None
        page = 0

        async with aiohttp.ClientSession(headers=self._headers) as session:
            while page < max_pages:
                payload: dict = {"page_size": 100}
                if filters:
                    payload["filter"] = filters
                if sorts:
                    payload["sorts"] = sorts
                if start_cursor:
                    payload["start_cursor"] = start_cursor

                try:
                    data = await self._request(session, "POST", url, payload)
                    all_results.extend(data.get("results", []))

                    if data.get("has_more") and data.get("next_cursor"):
                        start_cursor = data["next_cursor"]
                        page += 1
                    else:
                        break
                except Exception as e:
                    logger.warning("Erro na query (página %d): %s", page, e)
                    break

        return all_results

    async def query_parallel(self, queries: list[dict]) -> dict[str, list[dict]]:
        """Busca múltiplas collections em paralelo.

        Cada query: {"collection_id": str, "filters": dict, "label": str, "sorts": list}
        """
        results: dict[str, list[dict]] = {}

        async with aiohttp.ClientSession(headers=self._headers) as session:
            tasks = []
            labels = []

            for q in queries:
                collection_id = q.get("collection_id", "")
                if not collection_id:
                    results[q["label"]] = []
                    continue

                labels.append(q["label"])
                tasks.append(
                    self._query_with_session(
                        session,
                        collection_id,
                        q.get("filters"),
                        q.get("sorts"),
                        q.get("max_pages", 1),
                    )
                )

            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            for label, result in zip(labels, raw_results):
                if isinstance(result, Exception):
                    logger.warning("Falha em %s: %s", label, result)
                    results[label] = []
                else:
                    results[label] = result

        return results

    async def _query_with_session(
        self,
        session: aiohttp.ClientSession,
        collection_id: str,
        filters: dict | None,
        sorts: list | None,
        max_pages: int,
    ) -> list[dict]:
        """Query usando sessão compartilhada (para query_parallel)."""
        url = f"{NOTION_BASE_URL}/databases/{collection_id}/query"
        all_results: list[dict] = []
        start_cursor = None
        page = 0

        while page < max_pages:
            payload: dict = {"page_size": 100}
            if filters:
                payload["filter"] = filters
            if sorts:
                payload["sorts"] = sorts
            if start_cursor:
                payload["start_cursor"] = start_cursor

            data = await self._request(session, "POST", url, payload)
            all_results.extend(data.get("results", []))

            if data.get("has_more") and data.get("next_cursor"):
                start_cursor = data["next_cursor"]
                page += 1
            else:
                break

        return all_results

    async def create_record(self, collection_id: str, properties: dict) -> dict:
        """Cria uma página em um database Notion."""
        url = f"{NOTION_BASE_URL}/pages"
        payload = {
            "parent": {"database_id": collection_id},
            "properties": properties,
        }

        async with aiohttp.ClientSession(headers=self._headers) as session:
            return await self._request(session, "POST", url, payload)

    async def update_record(self, record_id: str, properties: dict) -> dict:
        """Atualiza propriedades de uma página Notion."""
        url = f"{NOTION_BASE_URL}/pages/{record_id}"
        payload = {"properties": properties}

        async with aiohttp.ClientSession(headers=self._headers) as session:
            return await self._request(session, "PATCH", url, payload)

    def extract_text(self, record: dict) -> str:
        """Extrai plain_text de array rich_text do Notion."""
        if isinstance(record, list):
            return "".join(item.get("plain_text", "") for item in record)
        if isinstance(record, dict):
            # Suporta record completo (busca em properties)
            props = record.get("properties", {})
            texts = []
            for prop in props.values():
                prop_type = prop.get("type", "")
                if prop_type == "title":
                    texts.append("".join(t.get("plain_text", "") for t in prop.get("title", [])))
                elif prop_type == "rich_text":
                    texts.append(
                        "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
                    )
            return " ".join(t for t in texts if t)
        return ""

    async def search_databases(self, name_prefix: str = "Vera") -> list[dict]:
        """Busca databases acessíveis pela integração (para auto-discovery no setup)."""
        url = f"{NOTION_BASE_URL}/search"
        payload = {
            "filter": {"value": "database", "property": "object"},
            "page_size": 100,
        }

        async with aiohttp.ClientSession(headers=self._headers) as session:
            data = await self._request(session, "POST", url, payload)

        results = []
        for db in data.get("results", []):
            title_parts = db.get("title", [])
            title = "".join(t.get("plain_text", "") for t in title_parts)
            if title.startswith(name_prefix):
                results.append({"id": db["id"], "title": title})

        return results
