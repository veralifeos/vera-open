"""Testes dos domínios de vida."""

import asyncio

import pytest

from vera.backends.base import StorageBackend
from vera.domains import DOMAIN_REGISTRY
from vera.domains.base import Domain
from vera.domains.contacts import ContactsDomain
from vera.domains.pipeline import PipelineDomain
from vera.domains.tasks import TasksDomain

# ─── Fixtures ────────────────────────────────────────────────────────────────


class MockBackend(StorageBackend):
    """Backend mock para testes."""

    def __init__(self, data: list[dict] | None = None):
        self._data = data or []

    async def query(self, collection_id, filters=None, sorts=None, max_pages=1):
        return self._data

    async def query_parallel(self, queries):
        return {q["label"]: self._data for q in queries}

    async def create_record(self, collection_id, properties):
        return {"id": "new", **properties}

    async def update_record(self, record_id, properties):
        return {"id": record_id, **properties}

    def extract_text(self, record):
        return ""


def _task_record(name: str, status: str = "To Do", deadline: str | None = None) -> dict:
    """Cria um record de tarefa no formato Notion."""
    record: dict = {
        "id": f"task_{name.lower().replace(' ', '_')}",
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": name}]},
            "Status": {"type": "status", "status": {"name": status}},
            "Prioridade": {"type": "select", "select": {"name": "Alta"}},
            "Tipo": {"type": "select", "select": {"name": "Trabalho"}},
            "Deadline": {"type": "date", "date": None},
        },
    }
    if deadline:
        record["properties"]["Deadline"]["date"] = {"start": deadline}
    return record


# ─── Testes da interface ─────────────────────────────────────────────────────


def test_domain_e_abstrato():
    """Domain não pode ser instanciado diretamente."""
    with pytest.raises(TypeError):
        Domain({}, MockBackend())


def test_domain_metodos_obrigatorios():
    """Verifica métodos abstratos."""
    abstract_methods = Domain.__abstractmethods__
    assert {"collect", "analyze", "context"} == abstract_methods


# ─── Testes do registry ──────────────────────────────────────────────────────


def test_registry_contem_domains_builtin():
    """Registry contém tasks, pipeline e contacts."""
    assert "tasks" in DOMAIN_REGISTRY
    assert "pipeline" in DOMAIN_REGISTRY
    assert "contacts" in DOMAIN_REGISTRY


def test_registry_tasks_e_tasks_domain():
    """Registry mapeia 'tasks' para TasksDomain."""
    assert DOMAIN_REGISTRY["tasks"] is TasksDomain


# ─── Testes do TasksDomain ───────────────────────────────────────────────────


def test_tasks_domain_implementa_interface():
    """TasksDomain é subclasse de Domain."""
    assert issubclass(TasksDomain, Domain)


def test_tasks_collect_sem_collection():
    """Retorna lista vazia se collection não configurada."""
    backend = MockBackend()
    config = {"collection": "", "fields": {}}
    domain = TasksDomain(config, backend)
    result = asyncio.run(domain.collect())
    assert result == {"tarefas": []}


def test_tasks_collect_com_dados():
    """Coleta e parseia tarefas corretamente."""
    records = [
        _task_record("Tarefa 1", "To Do", "2026-03-10"),
        _task_record("Tarefa 2", "Doing", "2026-03-05"),
    ]
    backend = MockBackend(records)
    config = {
        "collection": "db123",
        "fields": {
            "title": "Name",
            "status": "Status",
            "priority": "Prioridade",
            "deadline": "Deadline",
            "category": "Tipo",
            "status_active": ["To Do", "Doing"],
        },
    }
    domain = TasksDomain(config, backend)
    result = asyncio.run(domain.collect())
    assert len(result["tarefas"]) == 2
    assert result["tarefas"][0]["titulo"] == "Tarefa 1"
    assert result["tarefas"][0]["status"] == "To Do"
    assert result["tarefas"][0]["deadline"] == "2026-03-10"


def test_tasks_analyze_identifica_atrasadas():
    """Analyze separa tarefas atrasadas."""
    config = {"collection": "db123", "fields": {}}
    backend = MockBackend()
    domain = TasksDomain(config, backend)

    data = {
        "tarefas": [
            {"titulo": "Atrasada", "deadline": "2020-01-01", "prioridade": "Alta"},
            {"titulo": "Futura", "deadline": "2099-12-31", "prioridade": "Média"},
            {"titulo": "Sem prazo", "deadline": None, "prioridade": ""},
        ]
    }
    analysis = domain.analyze(data)
    assert len(analysis["atrasadas"]) == 1
    assert analysis["atrasadas"][0]["titulo"] == "Atrasada"
    assert len(analysis["sem_deadline"]) == 1
    assert analysis["total"] == 3


def test_tasks_context_gera_texto():
    """Context gera texto legível."""
    config = {"collection": "db123", "fields": {}}
    backend = MockBackend()
    domain = TasksDomain(config, backend)

    data = {
        "tarefas": [
            {"titulo": "T1", "deadline": "2026-03-10", "prioridade": "Alta"},
        ]
    }
    analysis = {"total": 1, "atrasadas": [], "hoje": [], "sem_deadline": []}
    text = domain.context(data, analysis)
    assert "TAREFAS: 1 ativas" in text


def test_tasks_context_com_atrasadas():
    """Context inclui seção de atrasadas."""
    config = {"collection": "db123", "fields": {}}
    backend = MockBackend()
    domain = TasksDomain(config, backend)

    data = {"tarefas": []}
    atrasada = {"titulo": "Urgente", "deadline": "2020-01-01", "prioridade": "Alta"}
    analysis = {"total": 1, "atrasadas": [atrasada], "hoje": [], "sem_deadline": []}
    text = domain.context(data, analysis)
    assert "ATRASADAS" in text
    assert "Urgente" in text


def test_tasks_fields_customizados():
    """Funciona com nomes de campos customizados."""
    records = [
        {
            "id": "t1",
            "properties": {
                "Título": {"type": "title", "title": [{"plain_text": "Minha Tarefa"}]},
                "Estado": {"type": "select", "select": {"name": "Aberto"}},
                "Importância": {"type": "select", "select": {"name": "Crítica"}},
                "Prazo": {"type": "date", "date": {"start": "2026-04-01"}},
                "Área": {"type": "select", "select": {"name": "Projeto"}},
            },
        }
    ]
    backend = MockBackend(records)
    config = {
        "collection": "db123",
        "fields": {
            "title": "Título",
            "status": "Estado",
            "priority": "Importância",
            "deadline": "Prazo",
            "category": "Área",
            "status_active": ["Aberto", "Fazendo"],
        },
    }
    domain = TasksDomain(config, backend)
    result = asyncio.run(domain.collect())
    assert result["tarefas"][0]["titulo"] == "Minha Tarefa"
    assert result["tarefas"][0]["prioridade"] == "Crítica"


# ─── Testes do PipelineDomain ────────────────────────────────────────────────


def test_pipeline_domain_implementa_interface():
    """PipelineDomain é subclasse de Domain."""
    assert issubclass(PipelineDomain, Domain)


def test_pipeline_sem_collection():
    """Retorna vazio sem collection."""
    backend = MockBackend()
    domain = PipelineDomain({"collection": "", "fields": {}}, backend)
    result = asyncio.run(domain.collect())
    assert result == {"oportunidades": []}


# ─── Testes do ContactsDomain ────────────────────────────────────────────────


def test_contacts_domain_implementa_interface():
    """ContactsDomain é subclasse de Domain."""
    assert issubclass(ContactsDomain, Domain)


def test_contacts_sem_collection():
    """Retorna vazio sem collection."""
    backend = MockBackend()
    domain = ContactsDomain({"collection": "", "fields": {}}, backend)
    result = asyncio.run(domain.collect())
    assert result == {"contatos": []}


# ─── Testes do collect_completed ────────────────────────────────────────


def test_tasks_collect_completed_sem_collection():
    """Retorna lista vazia se collection não configurada."""
    backend = MockBackend()
    config = {"collection": "", "fields": {"status_done": ["Done"]}}
    domain = TasksDomain(config, backend)
    result = asyncio.run(domain.collect_completed())
    assert result == []


def test_tasks_collect_completed_com_dados():
    """Coleta tarefas concluídas."""
    records = [
        _task_record("Concluída 1", "Done", "2026-03-05"),
        _task_record("Concluída 2", "Done"),
    ]
    backend = MockBackend(records)
    config = {
        "collection": "db123",
        "fields": {
            "title": "Name",
            "status": "Status",
            "priority": "Prioridade",
            "deadline": "Deadline",
            "category": "Tipo",
            "status_done": ["Done"],
        },
    }
    domain = TasksDomain(config, backend)
    result = asyncio.run(domain.collect_completed())
    assert len(result) == 2
    assert result[0]["titulo"] == "Concluída 1"
    assert result[0]["status"] == "Done"
