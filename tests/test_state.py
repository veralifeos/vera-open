"""Testes do state management."""

import pytest

from vera.state import StateManager


@pytest.fixture
def state_mgr(tmp_path):
    return StateManager(state_dir=tmp_path)


@pytest.fixture
def tarefas_exemplo():
    return [
        {
            "id": "t1",
            "titulo": "Tarefa 1",
            "status": "To Do",
            "deadline": "2026-03-10",
            "prioridade": "Alta",
        },
        {
            "id": "t2",
            "titulo": "Tarefa 2",
            "status": "Doing",
            "deadline": "2026-03-05",
            "prioridade": "Média",
        },
        {"id": "t3", "titulo": "Tarefa 3", "status": "To Do", "deadline": None, "prioridade": ""},
    ]


# ─── load/save ───────────────────────────────────────────────────────────────


def test_load_state_vazio(state_mgr):
    """Retorna state vazio se arquivo não existe."""
    state = state_mgr.load()
    assert state["last_run_date"] is None
    assert state["mention_counts"] == {}
    assert state["last_snapshot"] == {}


def test_save_e_load_roundtrip(state_mgr):
    """Salva e carrega state preservando dados."""
    state = {
        "last_run_date": "2026-03-05",
        "mention_counts": {"t1": {"count": 3}},
        "last_snapshot": {},
    }
    state_mgr.save(state)
    loaded = state_mgr.load()
    assert loaded["last_run_date"] == "2026-03-05"
    assert loaded["mention_counts"]["t1"]["count"] == 3


def test_save_dry_run_nao_grava(state_mgr):
    """Dry run não grava arquivo."""
    state_mgr.save({"last_run_date": "2026-03-05"}, dry_run=True)
    assert not state_mgr.state_path.exists()


def test_load_state_corrompido(state_mgr):
    """State corrompido retorna state vazio."""
    state_mgr.state_path.parent.mkdir(parents=True, exist_ok=True)
    state_mgr.state_path.write_text("{{invalid json", encoding="utf-8")
    state = state_mgr.load()
    assert state["last_run_date"] is None


# ─── hash e idempotência ────────────────────────────────────────────────────


def test_compute_hash_deterministic(state_mgr):
    """Hash é determinístico para mesmo payload."""
    payload = {"tarefas": ["A", "B"]}
    h1 = state_mgr.compute_hash(payload)
    h2 = state_mgr.compute_hash(payload)
    assert h1 == h2
    assert len(h1) == 12


def test_compute_hash_diferente(state_mgr):
    """Hash muda com payload diferente."""
    h1 = state_mgr.compute_hash({"tarefas": ["A"]})
    h2 = state_mgr.compute_hash({"tarefas": ["A", "B"]})
    assert h1 != h2


def test_is_duplicate_mesma_data(state_mgr):
    """Duplicado se mesma data."""
    state = {"last_run_date": "2026-03-05", "last_payload_hash": "abc"}
    assert state_mgr.is_duplicate(state, "xyz", "2026-03-05") is True


def test_is_duplicate_mesmo_hash(state_mgr):
    """Duplicado se mesmo hash."""
    state = {"last_run_date": "2026-03-04", "last_payload_hash": "abc"}
    assert state_mgr.is_duplicate(state, "abc", "2026-03-05") is True


def test_not_duplicate(state_mgr):
    """Não é duplicado se data e hash diferentes."""
    state = {"last_run_date": "2026-03-04", "last_payload_hash": "abc"}
    assert state_mgr.is_duplicate(state, "xyz", "2026-03-05") is False


# ─── mention counts ─────────────────────────────────────────────────────────


def test_update_mention_counts_incrementa(state_mgr, tarefas_exemplo):
    """Incrementa contadores para tarefas ativas."""
    state = {"mention_counts": {}, "last_snapshot": {}}
    delta = {"em_cooldown": [], "zombies": []}
    state = state_mgr.update_mention_counts(state, tarefas_exemplo, delta)
    assert state["mention_counts"]["t1"]["count"] == 1
    assert state["mention_counts"]["t2"]["count"] == 1


def test_update_mention_counts_acumula(state_mgr, tarefas_exemplo):
    """Contadores acumulam entre runs."""
    state = {
        "mention_counts": {
            "t1": {
                "count": 3,
                "first_seen": "2026-03-01",
                "last_seen": "2026-03-04",
                "cooldown_until": None,
                "last_status": "To Do",
                "last_deadline": "2026-03-10",
            }
        },
        "last_snapshot": {},
    }
    delta = {"em_cooldown": [], "zombies": []}
    state = state_mgr.update_mention_counts(state, tarefas_exemplo, delta)
    assert state["mention_counts"]["t1"]["count"] == 4


def test_update_mention_counts_skip_cooldown(state_mgr, tarefas_exemplo):
    """Tarefas em cooldown não incrementam."""
    state = {
        "mention_counts": {"t1": {"count": 8, "cooldown_until": "2099-12-31"}},
        "last_snapshot": {},
    }
    delta = {"em_cooldown": ["t1"], "zombies": []}
    state = state_mgr.update_mention_counts(state, tarefas_exemplo, delta)
    assert state["mention_counts"]["t1"]["count"] == 8  # Não incrementou


# ─── zombies ─────────────────────────────────────────────────────────────────


def test_get_zombies(state_mgr):
    """Identifica tasks com count >= threshold."""
    state = {
        "mention_counts": {
            "t1": {"count": 8},
            "t2": {"count": 3},
            "t3": {"count": 10},
        }
    }
    zombies = state_mgr.get_zombies(state)
    assert "t1" in zombies
    assert "t3" in zombies
    assert "t2" not in zombies


def test_get_zombies_threshold_customizado(state_mgr):
    """Threshold customizável."""
    state = {"mention_counts": {"t1": {"count": 5}}}
    assert state_mgr.get_zombies(state, threshold=5) == ["t1"]
    assert state_mgr.get_zombies(state, threshold=6) == []


# ─── delta ───────────────────────────────────────────────────────────────────


def test_compute_delta_novas(state_mgr, tarefas_exemplo):
    """Detecta tarefas novas (sem snapshot anterior)."""
    state = {"last_snapshot": {}, "mention_counts": {}}
    delta = state_mgr.compute_delta(state, tarefas_exemplo, "2026-03-06")
    assert len(delta["novas"]) == 3


def test_compute_delta_removidas(state_mgr):
    """Detecta tarefas removidas."""
    state = {
        "last_snapshot": {"t_old": {"titulo": "Tarefa Antiga", "status": "To Do"}},
        "mention_counts": {},
    }
    delta = state_mgr.compute_delta(state, [], "2026-03-06")
    assert "Tarefa Antiga" in delta["removidas"]


def test_compute_delta_pioraram(state_mgr):
    """Detecta tarefas que pioraram (deadline antecipou)."""
    state = {
        "last_snapshot": {"t1": {"titulo": "T1", "deadline": "2026-03-15", "status": "To Do"}},
        "mention_counts": {},
    }
    tarefas = [{"id": "t1", "titulo": "T1", "status": "To Do", "deadline": "2026-03-10"}]
    delta = state_mgr.compute_delta(state, tarefas, "2026-03-06")
    assert "T1" in delta["pioraram"]


def test_compute_delta_zombie(state_mgr):
    """Detecta zombie com count >= threshold e sem mudança."""
    state = {
        "last_snapshot": {"t1": {"titulo": "T1", "status": "To Do", "deadline": "2026-03-10"}},
        "mention_counts": {
            "t1": {
                "count": 8,
                "last_status": "To Do",
                "last_deadline": "2026-03-10",
                "first_seen": "2026-02-01",
                "cooldown_until": None,
            }
        },
    }
    tarefas = [{"id": "t1", "titulo": "T1", "status": "To Do", "deadline": "2026-03-10"}]
    delta = state_mgr.compute_delta(state, tarefas, "2026-03-06")
    assert len(delta["zombies"]) == 1
    assert delta["zombies"][0]["id"] == "t1"


def test_compute_delta_zombie_resetado(state_mgr):
    """Zombie reseta se status mudou."""
    state = {
        "last_snapshot": {"t1": {"titulo": "T1", "status": "To Do", "deadline": "2026-03-10"}},
        "mention_counts": {
            "t1": {
                "count": 8,
                "last_status": "To Do",
                "last_deadline": "2026-03-10",
                "cooldown_until": None,
            }
        },
    }
    # Status mudou para Doing
    tarefas = [{"id": "t1", "titulo": "T1", "status": "Doing", "deadline": "2026-03-10"}]
    delta = state_mgr.compute_delta(state, tarefas, "2026-03-06")
    assert len(delta["zombies"]) == 0


# ─── snapshot ────────────────────────────────────────────────────────────────


def test_build_snapshot(state_mgr, tarefas_exemplo):
    """Constrói snapshot com campos corretos."""
    snapshot = state_mgr.build_snapshot(tarefas_exemplo)
    assert "t1" in snapshot
    assert snapshot["t1"]["titulo"] == "Tarefa 1"
    assert snapshot["t1"]["status"] == "To Do"
    assert snapshot["t1"]["deadline"] == "2026-03-10"
