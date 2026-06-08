"""Cliente Notion sync — apenas para modulos pessoais (bot/astro).

Portado de vera-private/vera/integrations/notion_client.py. Sync via
requests, com retry exponencial (tenacity). Os modulos async do open
(vera/backends/notion.py) nao sao usados aqui — bot/astro rodam sync.

Funcoes expostas:
  - query_notion_database
  - create_notion_page
  - update_notion_page
  - fetch_notion_page (nova — usada pelo natal chart loader)
  - extrair_texto
"""

from __future__ import annotations

import logging
import time

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from vera.personal.config import NOTION_HEADERS

logger = logging.getLogger(__name__)

_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=2, min=2, max=30),
    "retry": retry_if_exception_type(requests.exceptions.RequestException),
    "reraise": True,
}


def query_notion_database(
    database_id: str,
    filter_obj: dict | None = None,
    sorts: list | None = None,
    max_pages: int = 10,
) -> dict:
    """Query sincrona com paginacao."""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    all_results: list = []
    start_cursor = None
    page = 0

    @retry(**_RETRY_KWARGS)
    def _post_with_retry(payload: dict) -> dict:
        response = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    while page < max_pages:
        payload: dict = {"page_size": 100}
        if filter_obj:
            payload["filter"] = filter_obj
        if sorts:
            payload["sorts"] = sorts
        if start_cursor:
            payload["start_cursor"] = start_cursor

        try:
            data = _post_with_retry(payload)
            all_results.extend(data.get("results", []))
            if data.get("has_more") and data.get("next_cursor"):
                start_cursor = data["next_cursor"]
                page += 1
                time.sleep(0.3)
            else:
                break
        except Exception as e:
            logger.warning("Erro na query Notion (pagina %d): %s", page, e)
            break

    return {"results": all_results}


@retry(**_RETRY_KWARGS)
def _create_page_with_retry(url: str, payload: dict) -> dict:
    response = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def create_notion_page(database_id: str, properties: dict) -> dict | None:
    """Cria pagina em um database Notion."""
    url = "https://api.notion.com/v1/pages"
    payload = {"parent": {"database_id": database_id}, "properties": properties}
    try:
        return _create_page_with_retry(url, payload)
    except Exception as e:
        logger.warning("Erro ao criar pagina Notion: %s", e)
        return None


@retry(**_RETRY_KWARGS)
def _patch_page_with_retry(url: str, payload: dict) -> dict:
    response = requests.patch(url, headers=NOTION_HEADERS, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def update_notion_page(page_id: str, properties: dict) -> dict | None:
    """Atualiza propriedades de uma pagina Notion."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": properties}
    try:
        return _patch_page_with_retry(url, payload)
    except Exception as e:
        logger.warning("Erro ao atualizar pagina Notion: %s", e)
        return None


@retry(**_RETRY_KWARGS)
def _get_page_with_retry(url: str) -> dict:
    response = requests.get(url, headers=NOTION_HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_notion_page(page_id: str) -> dict | None:
    """Busca metadados de uma pagina Notion pelo ID."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    try:
        return _get_page_with_retry(url)
    except Exception as e:
        logger.warning("Erro ao buscar pagina Notion %s: %s", page_id, e)
        return None


def fetch_notion_page_blocks(page_id: str, max_blocks: int = 100) -> list[dict]:
    """Busca o conteudo (blocks) de uma pagina Notion."""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    all_blocks: list[dict] = []
    start_cursor = None

    while len(all_blocks) < max_blocks:
        q_url = url
        if start_cursor:
            q_url = f"{url}?start_cursor={start_cursor}"
        try:
            data = _get_page_with_retry(q_url)
            all_blocks.extend(data.get("results", []))
            if data.get("has_more") and data.get("next_cursor"):
                start_cursor = data["next_cursor"]
            else:
                break
        except Exception as e:
            logger.warning("Erro ao buscar blocks Notion %s: %s", page_id, e)
            break

    return all_blocks


def extrair_texto(rich_text_array: list) -> str:
    """Extrai plain_text de array rich_text do Notion."""
    if not rich_text_array:
        return ""
    return "".join([item.get("plain_text", "") for item in rich_text_array])
