"""Testes do last_run."""

import json

import pytest

from vera.last_run import save_last_run


@pytest.fixture
def last_run_path(tmp_path):
    return tmp_path / "last_run.json"


def test_save_last_run_cria_arquivo(last_run_path):
    """Cria arquivo se não existe."""
    save_last_run("briefing", {"tarefas": 10}, last_run_path)
    assert last_run_path.exists()
    data = json.loads(last_run_path.read_text())
    assert data["briefing"]["tarefas"] == 10
    assert "timestamp" in data["briefing"]


def test_save_last_run_preserva_modos(last_run_path):
    """Preserva dados de outros modos."""
    save_last_run("briefing", {"tarefas": 10}, last_run_path)
    save_last_run("research", {"vagas": 5}, last_run_path)
    data = json.loads(last_run_path.read_text())
    assert "briefing" in data
    assert "research" in data
    assert data["briefing"]["tarefas"] == 10
    assert data["research"]["vagas"] == 5


def test_save_last_run_sobrescreve_modo(last_run_path):
    """Sobrescreve dados do mesmo modo."""
    save_last_run("briefing", {"tarefas": 10}, last_run_path)
    save_last_run("briefing", {"tarefas": 20}, last_run_path)
    data = json.loads(last_run_path.read_text())
    assert data["briefing"]["tarefas"] == 20


def test_save_last_run_arquivo_corrompido(last_run_path):
    """Arquivo corrompido é substituído."""
    last_run_path.write_text("{{invalid", encoding="utf-8")
    save_last_run("briefing", {"tarefas": 10}, last_run_path)
    data = json.loads(last_run_path.read_text())
    assert data["briefing"]["tarefas"] == 10
