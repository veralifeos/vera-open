"""Testes do briefing history."""

import pytest

from vera.briefing_history import (
    MAX_ENTRIES,
    MAX_WORDS_PER_ENTRY,
    _truncate,
    format_for_prompt,
    load_history,
    save_history,
)


@pytest.fixture
def history_path(tmp_path):
    return tmp_path / "briefing_history.json"


def test_load_history_vazio(history_path):
    """Retorna lista vazia se arquivo não existe."""
    assert load_history(history_path) == []


def test_save_e_load_roundtrip(history_path):
    """Salva e carrega preservando dados."""
    save_history("Briefing de teste", history_path)
    history = load_history(history_path)
    assert len(history) == 1
    assert "Briefing de teste" in history[0]["text"]
    assert "date" in history[0]
    assert "weekday" in history[0]


def test_circular_max_entries(history_path):
    """Mantém no máximo MAX_ENTRIES."""
    for i in range(MAX_ENTRIES + 3):
        save_history(f"Briefing {i}", history_path)
    history = load_history(history_path)
    assert len(history) == MAX_ENTRIES
    # Últimos devem ser os mais recentes
    assert f"Briefing {MAX_ENTRIES + 2}" in history[-1]["text"]


def test_truncate_texto_curto():
    """Texto curto não é truncado."""
    text = "Isto é um texto curto."
    assert _truncate(text) == text


def test_truncate_texto_longo():
    """Texto longo é truncado com '...'."""
    words = ["palavra"] * (MAX_WORDS_PER_ENTRY + 50)
    text = " ".join(words)
    result = _truncate(text)
    assert result.endswith("...")
    # Truncado para MAX_WORDS_PER_ENTRY palavras + "..." colado na última
    assert len(result.split()) <= MAX_WORDS_PER_ENTRY + 1


def test_format_for_prompt_vazio(history_path):
    """Prompt vazio se sem histórico."""
    assert format_for_prompt(history_path) == ""


def test_format_for_prompt_com_dados(history_path):
    """Prompt formatado com histórico."""
    save_history("Briefing A", history_path)
    save_history("Briefing B", history_path)
    prompt = format_for_prompt(history_path)
    assert "BRIEFINGS ANTERIORES" in prompt
    assert "Briefing A" in prompt
    assert "Briefing B" in prompt


def test_format_for_prompt_max_entries(history_path):
    """Respeita max_entries no prompt."""
    for i in range(5):
        save_history(f"Briefing {i}", history_path)
    prompt = format_for_prompt(history_path, max_entries=2)
    # Deve conter os 2 últimos
    assert "Briefing 4" in prompt
    assert "Briefing 3" in prompt
    assert "Briefing 0" not in prompt


def test_load_history_corrompido(history_path):
    """Arquivo corrompido retorna lista vazia."""
    history_path.write_text("{{not json", encoding="utf-8")
    assert load_history(history_path) == []
