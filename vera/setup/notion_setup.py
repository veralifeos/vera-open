"""Notion workspace provisioning — creates databases, samples, and welcome page.

One-time setup operation. Uses httpx (not aiohttp) per project convention.
"""

import asyncio
import logging
import os

import httpx

from vera.setup.schemas import (
    COMECE_AQUI_BLOCKS,
    DOMAIN_SCHEMAS,
    SAMPLE_DATA,
    record_to_notion_properties,
    schema_to_notion_properties,
)

logger = logging.getLogger(__name__)

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"

# Simple rate limiting: 3 req/s
_REQUEST_DELAY = 0.35  # seconds between requests


def _ssl_verify() -> bool:
    return os.environ.get("VERA_SSL_VERIFY", "1") != "0"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str,
    json: dict | None = None,
) -> dict:
    """Make a Notion API request with basic rate limiting."""
    await asyncio.sleep(_REQUEST_DELAY)
    resp = await client.request(method, url, headers=_headers(token), json=json)
    if resp.status_code >= 400:
        text = resp.text[:300]
        raise httpx.HTTPStatusError(
            f"Notion API {resp.status_code}: {text}",
            request=resp.request,
            response=resp,
        )
    return resp.json()


async def find_accessible_pages(token: str) -> list[dict]:
    """Search for pages the integration can access.

    Returns: [{"id": str, "title": str}, ...]
    """
    payload = {
        "filter": {"value": "page", "property": "object"},
        "page_size": 20,
    }
    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=15) as client:
        data = await _request(client, "POST", f"{NOTION_BASE_URL}/search", token, payload)

    pages = []
    for page in data.get("results", []):
        props = page.get("properties", {})
        title = ""
        # Try to extract title from properties
        for prop in props.values():
            if prop.get("type") == "title":
                title = "".join(
                    t.get("plain_text", "") for t in prop.get("title", [])
                )
                break
        if not title:
            title = f"Página {page['id'][:8]}..."
        pages.append({"id": page["id"], "title": title})

    return pages


async def create_vera_page(token: str, parent_page_id: str) -> str:
    """Create the 'Vera Life OS' parent page under the selected page.

    Returns: new page ID
    """
    payload = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": [{"type": "text", "text": {"content": "Vera Life OS"}}]
        },
        "icon": {"type": "emoji", "emoji": "🧠"},
    }
    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=15) as client:
        data = await _request(client, "POST", f"{NOTION_BASE_URL}/pages", token, payload)
    return data["id"]


async def create_database(
    token: str, parent_id: str, title: str, schema: list[dict]
) -> str:
    """Create a Notion database with the given schema under a parent page.

    Returns: new database ID
    """
    properties = schema_to_notion_properties(schema)
    payload = {
        "parent": {"page_id": parent_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }
    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=15) as client:
        data = await _request(
            client, "POST", f"{NOTION_BASE_URL}/databases", token, payload
        )
    return data["id"]


async def create_sample_records(
    token: str, db_id: str, records: list[dict], schema: list[dict]
) -> list[str]:
    """Create sample records in a database.

    Returns: list of created page IDs
    """
    created_ids = []
    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=15) as client:
        for record in records:
            properties = record_to_notion_properties(record, schema)
            payload = {
                "parent": {"database_id": db_id},
                "properties": properties,
            }
            data = await _request(
                client, "POST", f"{NOTION_BASE_URL}/pages", token, payload
            )
            created_ids.append(data["id"])
    return created_ids


async def create_comece_aqui_page(
    token: str, parent_id: str, db_ids: dict[str, str]
) -> str:
    """Create the 'Comece Aqui' welcome page with instructions.

    Returns: new page ID
    """
    # Build database links paragraph
    db_links_text = "Seus databases:\n"
    for domain, db_id in db_ids.items():
        display_name = DOMAIN_SCHEMAS.get(domain, (domain, []))[0]
        db_links_text += f"• {display_name}: {db_id[:8]}...\n"

    blocks = list(COMECE_AQUI_BLOCKS)  # copy
    # Insert DB links before the last paragraph
    blocks.insert(
        -1,
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": db_links_text}}
                ]
            },
        },
    )

    payload = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [{"type": "text", "text": {"content": "Comece Aqui"}}]
        },
        "icon": {"type": "emoji", "emoji": "👋"},
        "children": blocks,
    }
    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=15) as client:
        data = await _request(
            client, "POST", f"{NOTION_BASE_URL}/pages", token, payload
        )
    return data["id"]


async def provision_workspace(
    token: str, parent_page_id: str, domains: list[str]
) -> dict[str, str]:
    """Orchestrate full workspace creation.

    Creates "Vera Life OS" page, databases for each domain, sample records,
    and a "Comece Aqui" welcome page.

    Args:
        token: Notion integration token
        parent_page_id: ID of the page to create workspace under
        domains: list of domain names to create (e.g. ["tasks", "pipeline"])

    Returns: {domain_name: database_id}
    """
    # 1. Create parent page
    vera_page_id = await create_vera_page(token, parent_page_id)
    logger.info("Created Vera Life OS page: %s", vera_page_id)

    # 2. Create databases
    db_ids: dict[str, str] = {}
    for domain in domains:
        if domain not in DOMAIN_SCHEMAS:
            logger.warning("Unknown domain: %s, skipping", domain)
            continue

        title, schema = DOMAIN_SCHEMAS[domain]
        db_id = await create_database(token, vera_page_id, title, schema)
        db_ids[domain] = db_id
        logger.info("Created database %s: %s", title, db_id)

        # 3. Create sample records if available
        samples = SAMPLE_DATA.get(domain, [])
        if samples:
            await create_sample_records(token, db_id, samples, schema)
            logger.info("Created %d sample records for %s", len(samples), domain)

    # 4. Create welcome page
    await create_comece_aqui_page(token, vera_page_id, db_ids)
    logger.info("Created Comece Aqui page")

    return db_ids
