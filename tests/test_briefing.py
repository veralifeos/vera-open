"""Testes do briefing pipeline."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.backends.base import StorageBackend
from vera.config import VeraConfig
from vera.modes.briefing import (
    MAX_TAREFAS_PROMPT,
    _get_system_prompt,
    carregar_workspace_files,
    filtrar_e_rankear,
    gerar_briefing,
    montar_contexto,
    montar_contexto_domingo,
    montar_contexto_sabado,
    run_async,
    score_tarefa,
    verificar_janela_horario,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


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


class MockLLM:
    async def generate(self, system_prompt, user_prompt, max_tokens=1000, temperature=0.7):
        return "VERA — Briefing gerado pelo mock."

    async def generate_structured(self, system_prompt, user_prompt, schema, max_tokens=1000):
        return {}


def _tarefa(id, titulo, status="To Do", deadline=None, prioridade="Alta"):
    return {
        "id": id,
        "titulo": titulo,
        "status": status,
        "deadline": deadline,
        "prioridade": prioridade,
        "categoria": "",
    }


# ─── Guards ──────────────────────────────────────────────────────────────────


def test_janela_horario_force():
    """Force ignora janela."""
    config = _minimal_config()
    assert verificar_janela_horario(config, force=True) is True


def test_janela_horario_env_force():
    """FORCE_RUN=true ignora janela."""
    config = _minimal_config()
    with patch.dict("os.environ", {"FORCE_RUN": "true"}):
        assert verificar_janela_horario(config) is True


# ─── Scoring ─────────────────────────────────────────────────────────────────


def test_score_tarefa_atrasada():
    """Tarefa atrasada tem score alto."""
    t = _tarefa("t1", "Atrasada", deadline="2020-01-01")
    score = score_tarefa(t, {})
    assert score >= 100


def test_score_tarefa_hoje():
    """Tarefa com deadline hoje tem score alto."""
    hoje = datetime.now().strftime("%Y-%m-%d")
    t = _tarefa("t1", "Hoje", deadline=hoje)
    score = score_tarefa(t, {})
    assert score >= 80


def test_score_tarefa_mention_reduz():
    """Mention count reduz score."""
    t = _tarefa("t1", "Repetida", deadline="2020-01-01")
    mc = {"t1": {"count": 5}}
    score_com_mc = score_tarefa(t, mc)
    score_sem_mc = score_tarefa(t, {})
    assert score_com_mc < score_sem_mc


def test_score_prioridade_alta():
    """Prioridade alta aumenta score."""
    t_alta = _tarefa("t1", "Alta", prioridade="Alta")
    t_baixa = _tarefa("t2", "Baixa", prioridade="Baixa")
    assert score_tarefa(t_alta, {}) > score_tarefa(t_baixa, {})


# ─── Ranking ─────────────────────────────────────────────────────────────────


def test_filtrar_e_rankear_ordena():
    """Rankeia por score decrescente."""
    tarefas = [
        _tarefa("t1", "Futura", deadline="2099-12-31"),
        _tarefa("t2", "Atrasada", deadline="2020-01-01"),
    ]
    state = {"mention_counts": {}}
    delta = {"em_cooldown": [], "zombies": []}
    result = filtrar_e_rankear(tarefas, state, delta)
    assert result[0]["titulo"] == "Atrasada"


def test_filtrar_e_rankear_exclui_cooldown():
    """Exclui tarefas em cooldown."""
    tarefas = [_tarefa("t1", "Normal"), _tarefa("t2", "Cooldown")]
    state = {"mention_counts": {}}
    delta = {"em_cooldown": ["t2"], "zombies": []}
    result = filtrar_e_rankear(tarefas, state, delta)
    assert len(result) == 1
    assert result[0]["titulo"] == "Normal"


def test_filtrar_e_rankear_exclui_zombies():
    """Exclui tarefas zombie."""
    tarefas = [_tarefa("t1", "Normal"), _tarefa("t2", "Zombie")]
    state = {"mention_counts": {}}
    delta = {"em_cooldown": [], "zombies": [{"id": "t2", "titulo": "Zombie", "count": 8, "first_seen": ""}]}
    result = filtrar_e_rankear(tarefas, state, delta)
    assert len(result) == 1


def test_filtrar_e_rankear_max_prompt():
    """Limita a MAX_TAREFAS_PROMPT."""
    tarefas = [_tarefa(f"t{i}", f"Tarefa {i}") for i in range(30)]
    state = {"mention_counts": {}}
    delta = {"em_cooldown": [], "zombies": []}
    result = filtrar_e_rankear(tarefas, state, delta)
    assert len(result) == MAX_TAREFAS_PROMPT


# ─── Contexto ────────────────────────────────────────────────────────────────


def test_montar_contexto_basico():
    """Contexto contém seções esperadas."""
    tarefas = [_tarefa("t1", "Minha Tarefa", deadline="2026-03-10")]
    delta = {"novas": ["Nova Tarefa"], "pioraram": [], "em_cooldown": [], "zombies": []}
    ctx = montar_contexto(tarefas, delta, [], {}, {}, {}, "2026-03-06", 2)
    assert "TAREFAS PRIORITÁRIAS" in ctx
    assert "Minha Tarefa" in ctx
    assert "ENTRARAM NO RADAR HOJE" in ctx
    assert "Nova Tarefa" in ctx


def test_montar_contexto_com_mention():
    """Mention counts aparecem no contexto."""
    tarefas = [_tarefa("t1", "Repetida")]
    mc = {"t1": {"count": 5}}
    ctx = montar_contexto(tarefas, {"novas": [], "pioraram": []}, [], {}, mc, {}, "2026-03-06", 2)
    assert "citada 5x" in ctx


def test_montar_contexto_zombies():
    """Zombies aparecem no contexto."""
    zombies = [{"titulo": "Zumbi", "count": 9, "first_seen": "2026-02-01"}]
    ctx = montar_contexto([], {"novas": [], "pioraram": []}, zombies, {}, {}, {}, "2026-03-06", 2)
    assert "TAREFAS ZUMBI" in ctx
    assert "Zumbi" in ctx


def test_montar_contexto_domain_contexts():
    """Domain contexts são injetados."""
    domain_contexts = {"pipeline": "PIPELINE: 5 oportunidades"}
    ctx = montar_contexto([], {"novas": [], "pioraram": []}, [], domain_contexts, {}, {}, "2026-03-06", 2)
    assert "PIPELINE: 5 oportunidades" in ctx


def test_montar_contexto_sabado():
    """Contexto de sábado tem formato específico."""
    tarefas = [_tarefa("t1", "Tarefa 1")]
    ctx = montar_contexto_sabado(tarefas, {"novas": []}, [], {}, {}, "2026-03-07")
    assert "Sábado" in ctx
    assert "retrospectiva" in ctx.lower()


def test_montar_contexto_domingo():
    """Contexto de domingo tem formato específico."""
    tarefas = [_tarefa("t1", "Tarefa 1", deadline="2026-03-10")]
    ctx = montar_contexto_domingo(tarefas, [], {}, {}, "2026-03-08")
    assert "Domingo" in ctx
    assert "planejamento" in ctx.lower()


# ─── Persona / system prompt ────────────────────────────────────────────────


def test_get_system_prompt_executive():
    """Preset executive gera prompt com nome."""
    config = _minimal_config()
    prompt = _get_system_prompt(config, {})
    assert "Vera" in prompt
    assert "secretaria" in prompt.lower() or "executiva" in prompt.lower()


def test_get_system_prompt_custom():
    """Custom usa AGENT.md."""
    config = _minimal_config(persona={"preset": "custom", "custom_prompt_file": None})
    workspace = {"AGENT.md": "Sou uma persona customizada."}
    prompt = _get_system_prompt(config, workspace)
    assert "persona customizada" in prompt


# ─── Geração via LLM ────────────────────────────────────────────────────────


def test_gerar_briefing_weekday():
    """Gera briefing para dia de semana."""
    llm = MockLLM()
    config = _minimal_config()
    result = asyncio.run(
        gerar_briefing(llm, "system", "contexto", 2, "VERA — Quarta", config)
    )
    assert "VERA" in result


def test_gerar_briefing_sabado():
    """Gera briefing para sábado."""
    llm = MockLLM()
    config = _minimal_config()
    result = asyncio.run(
        gerar_briefing(llm, "system", "contexto", 5, "VERA — Sábado", config)
    )
    assert "VERA" in result


def test_gerar_briefing_domingo():
    """Gera briefing para domingo."""
    llm = MockLLM()
    config = _minimal_config()
    result = asyncio.run(
        gerar_briefing(llm, "system", "contexto", 6, "VERA — Domingo", config)
    )
    assert "VERA" in result


def test_gerar_briefing_erro_llm():
    """Erro no LLM retorna mensagem de erro."""
    class FailLLM:
        async def generate(self, **kwargs):
            raise Exception("API down")

    llm = FailLLM()
    config = _minimal_config()
    result = asyncio.run(
        gerar_briefing(llm, "system", "contexto", 2, "VERA — Quarta", config)
    )
    assert "Erro técnico" in result


# ─── Pipeline completo ──────────────────────────────────────────────────────


def test_run_async_dry_run(tmp_path):
    """Pipeline completo em dry run."""
    config = _minimal_config()

    task_records = [
        {
            "id": "t1",
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": "Tarefa Teste"}]},
                "Status": {"type": "status", "status": {"name": "To Do"}},
                "Prioridade": {"type": "select", "select": {"name": "Alta"}},
                "Deadline": {"type": "date", "date": {"start": "2026-03-10"}},
                "Tipo": {"type": "select", "select": None},
            },
        }
    ]
    backend = MockBackend(task_records)
    llm = MockLLM()

    with patch("vera.modes.briefing.StateManager") as MockState:
        mock_mgr = MagicMock()
        mock_mgr.load.return_value = {"last_run_date": None, "last_payload_hash": None,
                                       "mention_counts": {}, "last_snapshot": {}, "briefing_count": 0}
        mock_mgr.compute_hash.return_value = "abc123"
        mock_mgr.is_duplicate.return_value = False
        mock_mgr.compute_delta.return_value = {"novas": ["Tarefa Teste"], "pioraram": [],
                                                 "removidas": [], "zombies": [], "em_cooldown": []}
        mock_mgr.update_mention_counts.return_value = mock_mgr.load.return_value
        mock_mgr.build_snapshot.return_value = {}
        MockState.return_value = mock_mgr

        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            result = asyncio.run(run_async(config, backend, llm, force=True, dry_run=True))

    assert result is not None
    assert "VERA" in result
    # Dry run: state.save não é chamado
    mock_mgr.save.assert_not_called()


def test_run_async_idempotente(tmp_path):
    """Pipeline aborta se duplicado."""
    config = _minimal_config()
    backend = MockBackend([])
    llm = MockLLM()

    with patch("vera.modes.briefing.StateManager") as MockState:
        mock_mgr = MagicMock()
        mock_mgr.load.return_value = {"last_run_date": "2026-03-06", "last_payload_hash": "abc",
                                       "mention_counts": {}, "last_snapshot": {}, "briefing_count": 1}
        mock_mgr.compute_hash.return_value = "abc"
        mock_mgr.is_duplicate.return_value = True
        MockState.return_value = mock_mgr

        with patch("vera.modes.briefing.verificar_janela_horario", return_value=True):
            result = asyncio.run(run_async(config, backend, llm, force=False, dry_run=True))

    assert result is None  # Abortou por idempotência
