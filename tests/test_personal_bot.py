"""Testes do bot pessoal — parse + dispatch."""

from unittest.mock import patch

import vera.personal.bot as bot_mod
from vera.personal.bot import parse_command, process_message


# --- parse_command -------------------------------------------------------


def test_parse_status_no_args():
    cmd, args = parse_command("/status")
    assert cmd == "/status"
    assert args == []


def test_parse_check_with_args():
    cmd, args = parse_command("/check 7 6 8 5")
    assert cmd == "/check"
    assert args == ["7", "6", "8", "5"]


def test_parse_feito_multiword():
    cmd, args = parse_command("/feito detector furada")
    assert cmd == "/feito"
    assert args == ["detector", "furada"]


def test_parse_strips_bot_suffix():
    cmd, args = parse_command("/status@vera_bot")
    assert cmd == "/status"


def test_parse_non_command_returns_none():
    cmd, args = parse_command("oi vera")
    assert cmd is None
    assert args == []


# --- process_message -----------------------------------------------------


def test_process_unknown_command_returns_help():
    resp, state, pending = process_message("/banana", {})
    assert "nao reconhecido" in resp.lower() or "Comandos" in resp
    assert pending is None


def test_process_plain_text_ignored():
    resp, state, pending = process_message("oi", {})
    assert resp == ""


def test_process_numeric_resolves_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mod, "_BOT_PENDING_PATH", tmp_path / "bot_pending.json")
    (tmp_path / "bot_pending.json").write_text(
        '{"command": "feito", "options": [{"id": "abc", "nome": "Task", "status": "Doing"}]}',
        encoding="utf-8",
    )
    with patch.object(bot_mod, "update_notion_page", return_value={}):
        resp, state, pending = process_message("1", {})
    assert "Feito: Task" in resp
    assert not (tmp_path / "bot_pending.json").exists()


# --- cmd_check validation ------------------------------------------------


def test_cmd_check_validates_count(monkeypatch):
    monkeypatch.setattr(bot_mod, "NOTION_DB_CHECK", "fake_db")
    resp = bot_mod.cmd_check(["7", "6", "8"])
    assert "Formato" in resp


def test_cmd_check_validates_range(monkeypatch):
    monkeypatch.setattr(bot_mod, "NOTION_DB_CHECK", "fake_db")
    resp = bot_mod.cmd_check(["7", "6", "11", "5"])
    assert "fora do range" in resp


def test_cmd_check_requires_db(monkeypatch):
    monkeypatch.setattr(bot_mod, "NOTION_DB_CHECK", "")
    resp = bot_mod.cmd_check(["7", "6", "8", "5"])
    assert "nao configurado" in resp.lower()
