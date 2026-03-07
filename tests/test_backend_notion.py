"""Testes do StorageBackend e NotionBackend."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from vera.backends.base import StorageBackend
from vera.backends.notion import NotionBackend

# ─── Testes da interface ─────────────────────────────────────────────────────


def test_storage_backend_e_abstrato():
    """StorageBackend não pode ser instanciado diretamente."""
    with pytest.raises(TypeError):
        StorageBackend()


def test_storage_backend_metodos_obrigatorios():
    """Verifica que todos os métodos abstratos estão definidos."""
    abstract_methods = StorageBackend.__abstractmethods__
    expected = {"query", "query_parallel", "create_record", "update_record", "extract_text"}
    assert expected == abstract_methods


# ─── Testes do NotionBackend ─────────────────────────────────────────────────


def test_notion_backend_implementa_interface():
    """NotionBackend é subclasse de StorageBackend."""
    assert issubclass(NotionBackend, StorageBackend)


def test_notion_backend_sem_token_raises():
    """Erro claro se token não fornecido."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="Token Notion"):
            NotionBackend(token_env="NOTION_TOKEN_INEXISTENTE")


def test_notion_backend_com_token():
    """Cria instância com token direto."""
    backend = NotionBackend(token="ntnl_test_token")
    assert backend._token == "ntnl_test_token"
    assert "Bearer ntnl_test_token" in backend._headers["Authorization"]


def test_notion_backend_com_env_var():
    """Cria instância com env var."""
    with patch.dict("os.environ", {"MY_NOTION": "ntnl_env_token"}):
        backend = NotionBackend(token_env="MY_NOTION")
        assert backend._token == "ntnl_env_token"


# ─── Testes de query (mockados) ──────────────────────────────────────────────


@pytest.fixture
def backend():
    return NotionBackend(token="ntnl_test")


def test_query_retorna_lista(backend):
    """Query retorna lista de dicts."""
    mock_response = {
        "results": [{"id": "1", "properties": {}}],
        "has_more": False,
    }

    with patch.object(backend, "_request", new_callable=AsyncMock, return_value=mock_response):
        results = asyncio.run(backend.query("db123"))
        assert isinstance(results, list)
        assert len(results) == 1


def test_query_parallel_retorna_dict(backend):
    """query_parallel retorna dict com labels."""
    mock_response = {
        "results": [{"id": "1"}],
        "has_more": False,
    }

    with patch.object(backend, "_request", new_callable=AsyncMock, return_value=mock_response):
        queries = [
            {"collection_id": "db1", "label": "tarefas"},
            {"collection_id": "db2", "label": "pipeline"},
        ]
        results = asyncio.run(backend.query_parallel(queries))
        assert "tarefas" in results
        assert "pipeline" in results


def test_query_parallel_collection_vazia(backend):
    """Collection sem ID retorna lista vazia."""
    queries = [
        {"collection_id": "", "label": "vazio"},
    ]
    results = asyncio.run(backend.query_parallel(queries))
    assert results["vazio"] == []


# ─── Testes de extract_text ──────────────────────────────────────────────────


def test_extract_text_rich_text_array(backend):
    """Extrai texto de array rich_text do Notion."""
    rich_text = [
        {"plain_text": "Hello "},
        {"plain_text": "World"},
    ]
    assert backend.extract_text(rich_text) == "Hello World"


def test_extract_text_record_completo(backend):
    """Extrai texto de um record completo com properties."""
    record = {
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "Minha Tarefa"}],
            },
            "Notas": {
                "type": "rich_text",
                "rich_text": [{"plain_text": "Detalhes aqui"}],
            },
        }
    }
    text = backend.extract_text(record)
    assert "Minha Tarefa" in text
    assert "Detalhes aqui" in text


def test_extract_text_lista_vazia(backend):
    """Lista vazia retorna string vazia."""
    assert backend.extract_text([]) == ""


def test_extract_text_string_vazia(backend):
    """Input não-dict/list retorna string vazia."""
    assert backend.extract_text("") == ""


# ─── Teste de create/update (mockados) ───────────────────────────────────────


def test_create_record(backend):
    """create_record chama API corretamente."""
    mock_response = {"id": "new_page_id", "object": "page"}

    with patch.object(backend, "_request", new_callable=AsyncMock, return_value=mock_response):
        result = asyncio.run(
            backend.create_record("db123", {"Name": {"title": [{"text": {"content": "Test"}}]}})
        )
        assert result["id"] == "new_page_id"


def test_update_record(backend):
    """update_record chama API corretamente."""
    mock_response = {"id": "page_id", "object": "page"}

    with patch.object(backend, "_request", new_callable=AsyncMock, return_value=mock_response):
        result = asyncio.run(
            backend.update_record("page_id", {"Status": {"status": {"name": "Done"}}})
        )
        assert result["id"] == "page_id"
