"""Tests for vera.setup.notion_setup — Notion API calls mocked."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.setup.notion_setup import (
    create_comece_aqui_page,
    create_database,
    create_sample_records,
    create_vera_page,
    find_accessible_pages,
    provision_workspace,
)
from vera.setup.schemas import (
    DOMAIN_SCHEMAS,
    SAMPLE_DATA,
    TASKS_SCHEMA,
    record_to_notion_properties,
    schema_to_notion_properties,
)


# ─── Schema Converter Tests ─────────────────────────────────────────────────


def test_schema_to_notion_properties_tasks():
    """Tasks schema converts to valid Notion properties."""
    props = schema_to_notion_properties(TASKS_SCHEMA)
    assert "Name" in props
    assert "title" in props["Name"]
    assert "Status" in props
    assert "select" in props["Status"]
    assert len(props["Status"]["select"]["options"]) == 4
    assert "Deadline" in props
    assert "date" in props["Deadline"]


def test_schema_to_notion_properties_number():
    """Number fields get correct format."""
    schema = [{"name": "Score", "type": "number"}]
    props = schema_to_notion_properties(schema)
    assert props["Score"] == {"number": {"format": "number"}}


def test_record_to_notion_properties():
    """Sample record converts to Notion page properties."""
    record = {"Name": "Test task", "Status": "To Do", "Tipo": "Importante"}
    props = record_to_notion_properties(record, TASKS_SCHEMA)
    assert props["Name"]["title"][0]["text"]["content"] == "Test task"
    assert props["Status"]["select"]["name"] == "To Do"


# ─── API Call Tests (mocked) ────────────────────────────────────────────────


def _mock_client(responses):
    """Create a mock httpx.AsyncClient that returns given responses in order."""
    client = AsyncMock()
    if isinstance(responses, list):
        client.request.side_effect = responses
    else:
        client.request.return_value = responses
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _mock_response(status_code=200, json_data=None):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = ""
    resp.request = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_find_accessible_pages():
    """Finds pages the integration can access."""
    resp = _mock_response(200, {
        "results": [
            {
                "id": "page1",
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [{"plain_text": "My Page"}],
                    }
                },
            }
        ]
    })
    mock = _mock_client(resp)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        pages = await find_accessible_pages("token")

    assert len(pages) == 1
    assert pages[0]["title"] == "My Page"


@pytest.mark.asyncio
async def test_create_vera_page():
    """Creates Vera Life OS page."""
    resp = _mock_response(200, {"id": "new_page_id"})
    mock = _mock_client(resp)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        page_id = await create_vera_page("token", "parent_id")

    assert page_id == "new_page_id"


@pytest.mark.asyncio
async def test_create_database():
    """Creates a database with correct schema payload."""
    resp = _mock_response(200, {"id": "new_db_id"})
    mock = _mock_client(resp)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        db_id = await create_database("token", "parent_id", "Vera — Tasks", TASKS_SCHEMA)

    assert db_id == "new_db_id"
    # Verify the request payload
    call_args = mock.request.call_args
    payload = call_args.kwargs.get("json") or call_args[1].get("json")
    assert payload["title"][0]["text"]["content"] == "Vera — Tasks"
    assert "Name" in payload["properties"]


@pytest.mark.asyncio
async def test_create_sample_records():
    """Creates sample records in a database."""
    resp = _mock_response(200, {"id": "record_id"})
    mock = _mock_client(resp)

    samples = [{"Name": "Test", "Status": "To Do"}]

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        ids = await create_sample_records("token", "db_id", samples, TASKS_SCHEMA)

    assert len(ids) == 1
    assert ids[0] == "record_id"


@pytest.mark.asyncio
async def test_create_comece_aqui_page():
    """Creates welcome page with blocks."""
    resp = _mock_response(200, {"id": "welcome_id"})
    mock = _mock_client(resp)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        page_id = await create_comece_aqui_page("token", "parent_id", {"tasks": "db1"})

    assert page_id == "welcome_id"


@pytest.mark.asyncio
async def test_provision_workspace():
    """Full workspace provisioning orchestrates all steps."""
    # Mock responses: create_vera_page, create_database(tasks), create_sample(x2),
    # create_comece_aqui
    responses = [
        _mock_response(200, {"id": "vera_page_id"}),       # vera page
        _mock_response(200, {"id": "tasks_db_id"}),         # tasks database
        _mock_response(200, {"id": "sample1"}),             # sample record 1
        _mock_response(200, {"id": "sample2"}),             # sample record 2
        _mock_response(200, {"id": "welcome_id"}),          # comece aqui
    ]
    mock = _mock_client(responses)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        db_ids = await provision_workspace("token", "parent_page", ["tasks"])

    assert "tasks" in db_ids
    assert db_ids["tasks"] == "tasks_db_id"


@pytest.mark.asyncio
async def test_provision_workspace_multiple_domains():
    """Provisioning multiple domains creates all databases."""
    responses = [
        _mock_response(200, {"id": "vera_page_id"}),       # vera page
        _mock_response(200, {"id": "tasks_db_id"}),         # tasks db
        _mock_response(200, {"id": "s1"}),                  # sample 1
        _mock_response(200, {"id": "s2"}),                  # sample 2
        _mock_response(200, {"id": "pipeline_db_id"}),      # pipeline db (no samples)
        _mock_response(200, {"id": "contacts_db_id"}),      # contacts db
        _mock_response(200, {"id": "s3"}),                  # sample contact
        _mock_response(200, {"id": "check_db_id"}),         # check semanal db
        _mock_response(200, {"id": "s4"}),                  # sample check
        _mock_response(200, {"id": "welcome_id"}),          # comece aqui
    ]
    mock = _mock_client(responses)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        db_ids = await provision_workspace(
            "token", "parent_page",
            ["tasks", "pipeline", "contacts", "check_semanal"]
        )

    assert len(db_ids) == 4
    assert db_ids["tasks"] == "tasks_db_id"
    assert db_ids["pipeline"] == "pipeline_db_id"


@pytest.mark.asyncio
async def test_provision_workspace_unknown_domain():
    """Unknown domain is skipped."""
    responses = [
        _mock_response(200, {"id": "vera_page_id"}),
        _mock_response(200, {"id": "welcome_id"}),
    ]
    mock = _mock_client(responses)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        db_ids = await provision_workspace("token", "parent_page", ["nonexistent"])

    assert db_ids == {}


@pytest.mark.asyncio
async def test_create_database_error():
    """Database creation error propagates."""
    import httpx

    resp = _mock_response(400)
    resp.text = "Bad Request"
    mock = _mock_client(resp)

    with patch("vera.setup.notion_setup.httpx.AsyncClient", return_value=mock):
        with pytest.raises(httpx.HTTPStatusError):
            await create_database("token", "parent_id", "Test", TASKS_SCHEMA)
