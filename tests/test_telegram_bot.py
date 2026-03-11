"""Testes do Telegram bot (polling)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vera.integrations.telegram_bot import VeraBot


@pytest.fixture
def bot():
    return VeraBot("fake-token", "123456", config=None)


@pytest.fixture
def state_with_tasks(tmp_path):
    """Cria state com tarefas para testes."""
    state = {
        "last_run_date": "2026-03-11",
        "briefing_count": 5,
        "mention_counts": {
            "t1": {"count": 3, "first_seen": "2026-03-01", "last_seen": "2026-03-11", "cooldown_until": None},
            "t2": {"count": 9, "first_seen": "2026-02-01", "last_seen": "2026-03-10", "cooldown_until": None},
            "t3": {"count": 1, "first_seen": "2026-03-10", "last_seen": "2026-03-11", "cooldown_until": None},
        },
        "last_snapshot": {
            "t1": {"titulo": "Tarefa Urgente", "status": "To Do", "deadline": "2026-03-10", "prioridade": "Alta"},
            "t2": {"titulo": "Zumbi Antiga", "status": "To Do", "deadline": None, "prioridade": "Média"},
            "t3": {"titulo": "Tarefa Nova", "status": "Doing", "deadline": "2026-03-15", "prioridade": "Alta"},
        },
    }
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "briefing_state.json").write_text(json.dumps(state), encoding="utf-8")
    return tmp_path


class TestBotCommands:
    def test_cmd_help(self, bot):
        result = bot._cmd_help()
        assert "/status" in result
        assert "/next" in result
        assert "/help" in result

    def test_cmd_status_no_state(self, bot, tmp_path):
        with patch("vera.integrations.telegram_bot.StateManager") as MockSM:
            mock_mgr = MagicMock()
            mock_mgr.state_path = tmp_path / "nonexistent.json"
            MockSM.return_value = mock_mgr
            result = bot._cmd_status()
        assert "Nenhum state" in result

    def test_cmd_status_with_state(self, bot, state_with_tasks):
        with patch("vera.integrations.telegram_bot.StateManager") as MockSM:
            mock_mgr = MagicMock()
            mock_mgr.state_path = state_with_tasks / "state" / "briefing_state.json"
            MockSM.return_value = mock_mgr
            result = bot._cmd_status()
        assert "2026-03-11" in result
        assert "Briefings gerados: 5" in result
        assert "Zombies: 1" in result

    def test_cmd_next_no_state(self, bot, tmp_path):
        with patch("vera.integrations.telegram_bot.StateManager") as MockSM:
            mock_mgr = MagicMock()
            mock_mgr.state_path = tmp_path / "nonexistent.json"
            MockSM.return_value = mock_mgr
            result = bot._cmd_next()
        assert "Nenhum state" in result

    def test_cmd_next_with_tasks(self, bot, state_with_tasks):
        with patch("vera.integrations.telegram_bot.StateManager") as MockSM:
            mock_mgr = MagicMock()
            mock_mgr.state_path = state_with_tasks / "state" / "briefing_state.json"
            MockSM.return_value = mock_mgr
            result = bot._cmd_next()
        assert "Tarefa Urgente" in result
        assert "Tarefa Nova" in result
        # Zombie (t2) should not appear
        assert "Zumbi Antiga" not in result

    def test_cmd_next_excludes_zombies(self, bot, state_with_tasks):
        with patch("vera.integrations.telegram_bot.StateManager") as MockSM:
            mock_mgr = MagicMock()
            mock_mgr.state_path = state_with_tasks / "state" / "briefing_state.json"
            MockSM.return_value = mock_mgr
            result = bot._cmd_next()
        # t2 has count=9, should be excluded
        assert "Zumbi" not in result


class TestBotHandleUpdate:
    @pytest.mark.asyncio
    async def test_ignores_other_chats(self, bot):
        session = AsyncMock()
        update = {"message": {"chat": {"id": 999}, "text": "/status"}}
        # Should not send anything (different chat_id)
        with patch.object(bot, "_send") as mock_send:
            await bot._handle_update(session, update)
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_status_command(self, bot):
        session = AsyncMock()
        update = {"message": {"chat": {"id": 123456}, "text": "/status"}}
        with patch.object(bot, "_send") as mock_send:
            with patch.object(bot, "_cmd_status", return_value="status response"):
                await bot._handle_update(session, update)
                mock_send.assert_called_once_with(session, "status response")

    @pytest.mark.asyncio
    async def test_handles_unknown_command(self, bot):
        session = AsyncMock()
        update = {"message": {"chat": {"id": 123456}, "text": "/unknown"}}
        with patch.object(bot, "_send") as mock_send:
            await bot._handle_update(session, update)
            args = mock_send.call_args[0][1]
            assert "desconhecido" in args.lower()

    @pytest.mark.asyncio
    async def test_ignores_non_commands(self, bot):
        session = AsyncMock()
        update = {"message": {"chat": {"id": 123456}, "text": "hello"}}
        with patch.object(bot, "_send") as mock_send:
            await bot._handle_update(session, update)
            mock_send.assert_not_called()
