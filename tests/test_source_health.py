"""Testes do source health tracking."""

import pytest

from vera.source_health import SourceHealthTracker


@pytest.fixture
def tracker(tmp_path):
    return SourceHealthTracker(path=tmp_path / "source_health.json")


def test_record_incrementa_zeros(tracker):
    """Registra zero e incrementa contador."""
    tracker.record("fonte_a", 0)
    tracker.record("fonte_a", 0)
    tracker.record("fonte_a", 0)
    alerts = tracker.get_alerts(threshold=3)
    assert "fonte_a" in alerts


def test_record_reseta_com_resultado(tracker):
    """Resultado > 0 reseta o contador."""
    tracker.record("fonte_a", 0)
    tracker.record("fonte_a", 0)
    tracker.record("fonte_a", 5)  # Reseta
    tracker.record("fonte_a", 0)
    alerts = tracker.get_alerts(threshold=2)
    assert "fonte_a" not in alerts


def test_threshold_nao_atingido(tracker):
    """Abaixo do threshold nao gera alerta."""
    tracker.record("fonte_a", 0)
    tracker.record("fonte_a", 0)
    alerts = tracker.get_alerts(threshold=3)
    assert alerts == []


def test_multiplas_fontes(tracker):
    """Rastreia fontes independentemente."""
    for _ in range(3):
        tracker.record("boa", 10)
        tracker.record("ruim", 0)

    alerts = tracker.get_alerts(threshold=3)
    assert "ruim" in alerts
    assert "boa" not in alerts


def test_arquivo_inexistente(tracker):
    """Funciona sem arquivo existente."""
    alerts = tracker.get_alerts()
    assert alerts == []


def test_arquivo_corrompido(tracker):
    """Arquivo corrompido retorna vazio."""
    tracker._path.parent.mkdir(parents=True, exist_ok=True)
    tracker._path.write_text("{{invalid", encoding="utf-8")
    alerts = tracker.get_alerts()
    assert alerts == []


def test_format_for_briefing_vazio(tracker):
    """Sem alertas retorna string vazia."""
    assert tracker.format_for_briefing() == ""


def test_format_for_briefing_com_alertas(tracker):
    """Com alertas retorna texto formatado."""
    for _ in range(4):
        tracker.record("himalayas", 0)

    result = tracker.format_for_briefing(threshold=3)
    assert "ALERTAS DO SISTEMA" in result
    assert "himalayas" in result
    assert "4" in result
