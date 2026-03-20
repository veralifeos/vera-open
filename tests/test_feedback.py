"""Tests para o feedback loop: collector, tracker, writer."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from vera.feedback.collector import ObservationCollector
from vera.feedback.patterns import PatternEngine
from vera.feedback.tracker import BehaviorTracker, Signal
from vera.feedback.writer import UserProfileWriter


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_state(tmp_path):
    """Override state paths to use temp directory."""
    obs_path = tmp_path / "observations.json"
    inf_path = tmp_path / "inferences.json"
    return tmp_path, obs_path, inf_path


def _make_collector(tmp_path) -> ObservationCollector:
    collector = ObservationCollector()
    collector.STATE_PATH = tmp_path / "observations.json"
    return collector


def _make_observation(
    days_ago: int = 0,
    energy: int = 7,
    dia_num: int = 2,
    suggested: list | None = None,
    completed: list | None = None,
    mc_snapshot: dict | None = None,
    pack_results: dict | None = None,
) -> dict:
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    return {
        "date": d,
        "tasks_suggested": suggested or ["t1", "t2", "t3"],
        "tasks_completed": completed or [],
        "energy_score": energy,
        "dia_num": dia_num,
        "pack_results": pack_results or {},
        "mention_counts_snapshot": mc_snapshot or {},
    }


# ─── ObservationCollector ────────────────────────────────────────────────────


def test_collector_creates_file(tmp_path):
    """record() cria arquivo se não existe."""
    collector = _make_collector(tmp_path)
    collector.record({"tasks_suggested": ["t1"], "dia_num": 3})

    assert collector.STATE_PATH.exists()
    data = json.loads(collector.STATE_PATH.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["observations"]) == 1
    assert data["observations"][0]["dia_num"] == 3


def test_collector_appends(tmp_path):
    """record() appende à lista existente."""
    collector = _make_collector(tmp_path)
    collector.record({"tasks_suggested": ["t1"]})
    collector.record({"tasks_suggested": ["t2"]})
    collector.record({"tasks_suggested": ["t3"]})

    data = json.loads(collector.STATE_PATH.read_text(encoding="utf-8"))
    assert len(data["observations"]) == 3


def test_collector_handles_existing_file(tmp_path):
    """record() funciona com arquivo existente válido."""
    collector = _make_collector(tmp_path)

    # Pre-populate
    initial = {"version": 1, "observations": [_make_observation()], "weekly_snapshots": []}
    collector.STATE_PATH.write_text(json.dumps(initial), encoding="utf-8")

    collector.record({"tasks_suggested": ["new"]})

    data = json.loads(collector.STATE_PATH.read_text(encoding="utf-8"))
    assert len(data["observations"]) == 2


def test_collector_prunes_old(tmp_path):
    """record() remove observações mais velhas que 90 dias."""
    collector = _make_collector(tmp_path)

    old_date = (date.today() - timedelta(days=100)).isoformat()
    initial = {
        "version": 1,
        "observations": [{"date": old_date, "tasks_suggested": [], "tasks_completed": [],
                          "energy_score": 5, "dia_num": 0, "pack_results": {},
                          "mention_counts_snapshot": {}}],
        "weekly_snapshots": [],
    }
    collector.STATE_PATH.write_text(json.dumps(initial), encoding="utf-8")

    collector.record({"tasks_suggested": ["new"]})

    data = json.loads(collector.STATE_PATH.read_text(encoding="utf-8"))
    assert len(data["observations"]) == 1  # old one pruned
    assert data["observations"][0]["date"] == date.today().isoformat()


# ─── BehaviorTracker ─────────────────────────────────────────────────────────


def test_tracker_empty_with_few_observations():
    """Retorna lista vazia com menos de 5 observações."""
    tracker = BehaviorTracker()
    obs = [_make_observation(days_ago=i) for i in range(4)]
    signals = tracker.detect_signals(obs)
    assert signals == []


def test_tracker_no_signals_when_healthy():
    """Sem sinais quando tudo está saudável (energia alta, sem zombies)."""
    tracker = BehaviorTracker()
    obs = [_make_observation(days_ago=i, energy=8) for i in range(7)]
    signals = tracker.detect_signals(obs)
    # May have some signals but no carga/zona_morta
    carga = [s for s in signals if s.type == "carga"]
    assert len(carga) == 0


def test_tracker_detects_carga():
    """Detecta sinal de carga quando energia média < 5."""
    tracker = BehaviorTracker()
    obs = [_make_observation(days_ago=i, energy=3) for i in range(7)]
    signals = tracker.detect_signals(obs)

    carga = [s for s in signals if s.type == "carga"]
    assert len(carga) == 1
    assert carga[0].value["avg_energy"] == 3.0


def test_tracker_detects_zona_morta():
    """Detecta zona morta: task com mention_count >= 7 nunca concluída."""
    tracker = BehaviorTracker()
    obs = [
        _make_observation(
            days_ago=i,
            mc_snapshot={"task_zombie": 8, "task_ok": 2},
            completed=[],
        )
        for i in range(6)
    ]
    signals = tracker.detect_signals(obs)

    zona = [s for s in signals if s.type == "zona_morta"]
    assert len(zona) >= 1
    assert zona[0].value["task_id"] == "task_zombie"


def test_tracker_no_zona_morta_if_completed():
    """Não detecta zona morta se a task foi concluída em alguma observação."""
    tracker = BehaviorTracker()
    obs = [
        _make_observation(
            days_ago=i,
            mc_snapshot={"task_zombie": 8},
            completed=["task_zombie"] if i == 0 else [],
        )
        for i in range(6)
    ]
    signals = tracker.detect_signals(obs)

    zona = [s for s in signals if s.type == "zona_morta"]
    assert len(zona) == 0


def test_tracker_detects_prioridade_real():
    """Detecta prioridade real: task concluída com mention_count >= 4."""
    tracker = BehaviorTracker()
    obs = [
        _make_observation(
            days_ago=i,
            mc_snapshot={"task_done": 5},
            completed=["task_done"] if i == 0 else [],
        )
        for i in range(6)
    ]
    signals = tracker.detect_signals(obs)

    prio = [s for s in signals if s.type == "prioridade_real"]
    assert len(prio) == 1
    assert prio[0].value["task_id"] == "task_done"


# ─── PatternEngine ───────────────────────────────────────────────────────────


def test_pattern_carga_inference():
    """Sinal carga gera inferência com texto correto."""
    engine = PatternEngine()
    signals = [Signal("carga", {"avg_energy": 3.5, "days": 5}, 5, 0.8)]
    inferences = engine.generate_inferences(signals)

    assert len(inferences) == 1
    assert "Reduzir carga" in inferences[0].text
    assert "3.5" in inferences[0].text


def test_pattern_zona_morta_inference():
    """Sinal zona_morta gera inferência com 'remova esta linha'."""
    engine = PatternEngine()
    signals = [Signal("zona_morta", {"task_id": "task_x", "mention_count": 9}, 9, 0.8)]
    inferences = engine.generate_inferences(signals)

    assert len(inferences) == 1
    assert "remova esta linha se discordar" in inferences[0].text
    assert "task_x" in inferences[0].text


def test_pattern_skips_ritmo():
    """v1: ritmo e pack_irrelevante não geram inferências."""
    engine = PatternEngine()
    signals = [Signal("ritmo", {"weekday": 4, "ratio": 0.9}, 10, 0.9)]
    inferences = engine.generate_inferences(signals)
    assert len(inferences) == 0


# ─── UserProfileWriter ──────────────────────────────────────────────────────


def test_writer_creates_section_if_missing(tmp_path):
    """Writer cria ## Feedback loop se não existe."""
    user_md = tmp_path / "USER.md"
    user_md.write_text("# Meu perfil\n\n## Situação\nAtivo\n", encoding="utf-8")

    writer = UserProfileWriter()
    writer._save_active_inferences = lambda x: None  # stub state save

    # Patch paths
    import vera.feedback.writer as w
    original_path = w.USER_MD_PATH
    original_inf = w.INFERENCES_STATE_PATH
    w.USER_MD_PATH = user_md
    w.INFERENCES_STATE_PATH = tmp_path / "inferences.json"

    try:
        from vera.feedback.patterns import Inference
        inf = Inference("abc", "carga", "Teste", "2026-03-20", "2026-04-20", 5)
        result = writer.update([inf])

        content = user_md.read_text(encoding="utf-8")
        assert "## Feedback loop" in content
        assert "[inferido 2026-03-20]" in content
        assert result["added"] == 1
    finally:
        w.USER_MD_PATH = original_path
        w.INFERENCES_STATE_PATH = original_inf


def test_writer_does_not_modify_other_sections(tmp_path):
    """Writer NUNCA modifica seções acima de ## Feedback loop."""
    user_md = tmp_path / "USER.md"
    original_content = "# Perfil\n\n## Situação\nAtivo\n\n## Prioridades\n1. Vera\n"
    user_md.write_text(original_content + "\n## Feedback loop\nAnterior\n", encoding="utf-8")

    writer = UserProfileWriter()

    import vera.feedback.writer as w
    original_path = w.USER_MD_PATH
    original_inf = w.INFERENCES_STATE_PATH
    w.USER_MD_PATH = user_md
    w.INFERENCES_STATE_PATH = tmp_path / "inferences.json"

    try:
        from vera.feedback.patterns import Inference
        inf = Inference("xyz", "zona_morta", "Teste zona", "2026-03-20", "2026-04-20", 7)
        writer.update([inf])

        content = user_md.read_text(encoding="utf-8")

        # Sections above ## Feedback loop must be unchanged
        assert "# Perfil" in content
        assert "## Situação" in content
        assert "Ativo" in content
        assert "## Prioridades" in content
        assert "1. Vera" in content
        assert "[inferido 2026-03-20] Teste zona" in content
    finally:
        w.USER_MD_PATH = original_path
        w.INFERENCES_STATE_PATH = original_inf


def test_writer_respects_max_15(tmp_path):
    """Writer respeita limite de 15 inferências ativas."""
    user_md = tmp_path / "USER.md"
    user_md.write_text("# Perfil\n\n## Feedback loop\n", encoding="utf-8")

    writer = UserProfileWriter()

    import vera.feedback.writer as w
    original_path = w.USER_MD_PATH
    original_inf = w.INFERENCES_STATE_PATH
    w.USER_MD_PATH = user_md
    w.INFERENCES_STATE_PATH = tmp_path / "inferences.json"

    try:
        from vera.feedback.patterns import Inference

        # Create 20 inferences
        inferences = [
            Inference(f"id{i}", "carga", f"Inf {i}", f"2026-03-{i+1:02d}", "2026-05-01", 3)
            for i in range(20)
        ]
        result = writer.update(inferences)

        assert result["total"] <= 15
    finally:
        w.USER_MD_PATH = original_path
        w.INFERENCES_STATE_PATH = original_inf
