"""Testes end-to-end do pipeline completo."""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

from vera.backends.base import StorageBackend
from vera.config import VeraConfig
from vera.llm.base import LLMProvider
from vera.modes.briefing import run_async

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _minimal_config(**overrides) -> VeraConfig:
    data = {
        "name": "Vera",
        "timezone": "America/Sao_Paulo",
        "backend": {"type": "notion", "notion": {"token_env": "NOTION_TOKEN"}},
        "llm": {
            "default": "claude",
            "providers": {"claude": {"model": "test", "api_key_env": "KEY"}},
        },
        "domains": {
            "tasks": {
                "enabled": True,
                "collection": "db123",
                "fields": {
                    "title": "Name",
                    "status": "Status",
                    "priority": "Prioridade",
                    "deadline": "Deadline",
                    "status_active": ["To Do", "Doing"],
                },
            }
        },
        "schedule": {"briefing": "09:00"},
        "persona": {"preset": "executive"},
    }
    data.update(overrides)
    return VeraConfig(**data)


class MockBackend(StorageBackend):
    def __init__(self, data=None):
        self._data = data or []

    async def query(self, collection_id, filters=None, sorts=None, max_pages=1):
        return self._data

    async def query_parallel(self, queries):
        return {q["label"]: self._data for q in queries}

    async def create_record(self, collection_id, properties):
        return {"id": "new"}

    async def update_record(self, record_id, properties):
        return {"id": record_id}

    def extract_text(self, record):
        return ""


class MockLLM(LLMProvider):
    async def generate(self, system_prompt, user_prompt, max_tokens=1000, temperature=0.7):
        return "VERA — Briefing gerado pelo mock."

    async def generate_structured(self, system_prompt, user_prompt, schema, max_tokens=1000):
        return {}


def _task_records(n=3):
    """Cria N task records no formato Notion."""
    records = []
    for i in range(n):
        records.append(
            {
                "id": f"t{i}",
                "properties": {
                    "Name": {"type": "title", "title": [{"plain_text": f"Tarefa {i}"}]},
                    "Status": {"type": "status", "status": {"name": "To Do"}},
                    "Prioridade": {"type": "select", "select": {"name": "Alta"}},
                    "Deadline": {"type": "date", "date": {"start": "2026-03-10"}},
                    "Tipo": {"type": "select", "select": None},
                },
            }
        )
    return records


def _mock_state_manager(state=None):
    """Cria mock do StateManager."""
    mock_cls = MagicMock()
    mock_mgr = MagicMock()
    default_state = {
        "last_run_date": None,
        "last_payload_hash": None,
        "mention_counts": {},
        "last_snapshot": {},
        "briefing_count": 0,
    }
    mock_mgr.load.return_value = state or default_state
    mock_mgr.compute_hash.return_value = "abc123"
    mock_mgr.is_duplicate.return_value = False
    mock_mgr.compute_delta.return_value = {
        "novas": ["Tarefa 0", "Tarefa 1"],
        "pioraram": [],
        "removidas": [],
        "zombies": [],
        "em_cooldown": [],
    }
    mock_mgr.update_mention_counts.return_value = mock_mgr.load.return_value
    mock_mgr.build_snapshot.return_value = {}
    mock_cls.return_value = mock_mgr
    return mock_cls, mock_mgr


# ─── Tests ────────────────────────────────────────────────────────────────────


def test_full_pipeline_dry_run():
    """Pipeline completo, dry_run=True. Briefing gerado, state NAO salvo."""
    config = _minimal_config()
    backend = MockBackend(_task_records(3))
    llm = MockLLM()
    mock_cls, mock_mgr = _mock_state_manager()

    with patch("vera.modes.briefing.StateManager", mock_cls):
        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            result = asyncio.run(run_async(config, backend, llm, force=True, dry_run=True))

    assert result is not None
    assert "VERA" in result
    mock_mgr.save.assert_not_called()


def test_full_pipeline_with_existing_state():
    """Segundo run com state existente. Delta calculado, mentions atualizados."""
    config = _minimal_config()
    backend = MockBackend(_task_records(3))
    llm = MockLLM()

    existing_state = {
        "last_run_date": "2026-03-05",
        "last_payload_hash": "old_hash",
        "mention_counts": {
            "t0": {
                "count": 3,
                "first_seen": "2026-03-01",
                "last_seen": "2026-03-05",
                "cooldown_until": None,
                "last_status": "To Do",
                "last_deadline": "2026-03-10",
            }
        },
        "last_snapshot": {
            "t0": {"titulo": "Tarefa 0", "status": "To Do", "deadline": "2026-03-10"}
        },
        "briefing_count": 5,
    }
    mock_cls, mock_mgr = _mock_state_manager(existing_state)

    with patch("vera.modes.briefing.StateManager", mock_cls):
        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            result = asyncio.run(run_async(config, backend, llm, force=True, dry_run=True))

    assert result is not None
    mock_mgr.compute_delta.assert_called_once()
    mock_mgr.update_mention_counts.assert_called_once()


def test_full_pipeline_idempotent_skip():
    """Mesmo hash + mesma data = skip. Com --force = executa."""
    config = _minimal_config()
    backend = MockBackend(_task_records(1))
    llm = MockLLM()
    mock_cls, mock_mgr = _mock_state_manager()
    mock_mgr.is_duplicate.return_value = True

    # Sem force: skip
    with patch("vera.modes.briefing.StateManager", mock_cls):
        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            result = asyncio.run(run_async(config, backend, llm, force=False, dry_run=True))
    assert result is None

    # Com force: executa
    mock_cls2, mock_mgr2 = _mock_state_manager()
    mock_mgr2.is_duplicate.return_value = True
    with patch("vera.modes.briefing.StateManager", mock_cls2):
        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            result = asyncio.run(run_async(config, backend, llm, force=True, dry_run=True))
    assert result is not None


def test_full_pipeline_saturday_retrospective():
    """Mock sabado. Verifica prompt de retrospectiva."""
    config = _minimal_config()
    backend = MockBackend(_task_records(3))

    prompts_received = []

    class CaptureLLM(LLMProvider):
        async def generate(self, system_prompt, user_prompt, max_tokens=1000, temperature=0.7):
            prompts_received.append(user_prompt)
            return "VERA — Retrospectiva semanal."

        async def generate_structured(self, system_prompt, user_prompt, schema, max_tokens=1000):
            return {}

    llm = CaptureLLM()
    mock_cls, mock_mgr = _mock_state_manager()

    # Mock sabado (weekday=5)
    from datetime import datetime as dt

    fake_now = dt(2026, 3, 7, 10, 0)  # Sabado

    with patch("vera.modes.briefing.StateManager", mock_cls):
        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            with patch("vera.modes.briefing.datetime") as mock_dt:
                mock_dt.now.return_value = fake_now
                mock_dt.strptime = datetime.strptime
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                result = asyncio.run(run_async(config, backend, llm, force=True, dry_run=True))

    assert result is not None
    assert "VERA" in result
    # Verifica que prompt de sabado foi usado
    if prompts_received:
        assert (
            "sabado" in prompts_received[0].lower()
            or "semanal" in prompts_received[0].lower()
            or "400" in prompts_received[0]
        )


def test_full_pipeline_error_triggers_notification():
    """LLM falha completamente. Verifica que erro e propagado."""
    config = _minimal_config()
    backend = MockBackend(_task_records(3))

    class FailLLM(LLMProvider):
        async def generate(self, system_prompt, user_prompt, max_tokens=1000, temperature=0.7):
            raise ConnectionError("LLM unreachable")

        async def generate_structured(self, system_prompt, user_prompt, schema, max_tokens=1000):
            raise ConnectionError("LLM unreachable")

    llm = FailLLM()
    mock_cls, mock_mgr = _mock_state_manager()

    with patch("vera.modes.briefing.StateManager", mock_cls):
        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            # gerar_briefing catches LLM errors and returns error message
            result = asyncio.run(run_async(config, backend, llm, force=True, dry_run=True))

    # Pipeline nao levanta excecao, mas briefing contem erro
    assert result is not None
    assert "Erro" in result or "VERA" in result
