"""Telegram bot — polling-based command handler.

Supported commands:
  /status  — system status (last run, tasks, zombies)
  /next    — top 3 priority tasks
  /done ID — mark a task pattern as done (future)
  /help    — list commands
"""

import asyncio
import json
import logging
import os
import ssl

import aiohttp

from vera.state import StateManager

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class VeraBot:
    """Polling-based Telegram bot for Vera."""

    def __init__(self, bot_token: str, chat_id: str, config=None):
        self._token = bot_token
        self._chat_id = chat_id
        self._config = config
        self._offset = 0
        self._running = False

    async def start(self) -> None:
        """Start polling loop."""
        self._running = True
        print(f"   [bot] Iniciando polling (chat_id={self._chat_id})")

        ssl_ctx: ssl.SSLContext | bool | None = None
        if os.environ.get("VERA_SSL_VERIFY", "1") == "0":
            ssl_ctx = False

        connector = aiohttp.TCPConnector(ssl=ssl_ctx) if ssl_ctx is False else None
        async with aiohttp.ClientSession(connector=connector) as session:
            while self._running:
                try:
                    updates = await self._get_updates(session)
                    for update in updates:
                        await self._handle_update(session, update)
                except aiohttp.ClientError as e:
                    logger.warning("Bot polling error: %s", e)
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error("Bot unexpected error: %s", e)
                    await asyncio.sleep(5)

                await asyncio.sleep(1)

    def stop(self) -> None:
        """Stop polling loop."""
        self._running = False

    async def _get_updates(self, session: aiohttp.ClientSession) -> list[dict]:
        """Fetch new updates via long polling."""
        url = f"{TELEGRAM_API.format(token=self._token)}/getUpdates"
        params = {"offset": self._offset, "timeout": 30}
        timeout = aiohttp.ClientTimeout(total=35)

        async with session.get(url, params=params, timeout=timeout) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def _handle_update(self, session: aiohttp.ClientSession, update: dict) -> None:
        """Process a single update."""
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()

        # Only respond to configured chat
        if chat_id != self._chat_id:
            return

        if not text.startswith("/"):
            return

        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]  # strip @botname
        args = parts[1] if len(parts) > 1 else ""

        if command == "/status":
            response = self._cmd_status()
        elif command == "/next":
            response = self._cmd_next()
        elif command == "/help" or command == "/start":
            response = self._cmd_help()
        else:
            response = f"Comando desconhecido: {command}\nUse /help para ver comandos."

        await self._send(session, response)

    async def _send(self, session: aiohttp.ClientSession, text: str) -> None:
        """Send a message."""
        url = f"{TELEGRAM_API.format(token=self._token)}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text[:4096],
            "parse_mode": "Markdown",
        }
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with session.post(url, json=payload, timeout=timeout) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    # Retry without markdown if parse fails
                    if resp.status == 400 and "parse" in err.lower():
                        payload["parse_mode"] = None
                        async with session.post(url, json=payload, timeout=timeout):
                            pass
        except Exception as e:
            logger.error("Failed to send message: %s", e)

    def _cmd_help(self) -> str:
        """List available commands."""
        return (
            "*Vera Bot* — Comandos disponíveis:\n\n"
            "/status — Status do sistema (último run, tarefas, zombies)\n"
            "/next — Top 3 tarefas prioritárias\n"
            "/help — Esta mensagem"
        )

    def _cmd_status(self) -> str:
        """System status."""
        state_mgr = StateManager()
        state_path = state_mgr.state_path

        if not state_path.exists():
            return "Nenhum state encontrado. Rode `vera briefing` primeiro."

        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return "Erro ao ler state."

        last_run = state.get("last_run_date", "nunca")
        briefing_count = state.get("briefing_count", 0)
        mc = state.get("mention_counts", {})
        total_tasks = len(mc)
        zombies = sum(1 for v in mc.values() if v.get("count", 0) >= 8)
        cooldowns = sum(1 for v in mc.values() if v.get("cooldown_until"))

        # High mention tasks
        high_mc = sorted(
            [(v.get("count", 0), k) for k, v in mc.items() if v.get("count", 0) >= 4],
            reverse=True,
        )[:5]

        lines = [
            f"*Vera Status*\n",
            f"Último briefing: {last_run}",
            f"Briefings gerados: {briefing_count}",
            f"Tarefas rastreadas: {total_tasks}",
            f"Zombies: {zombies} | Cooldown: {cooldowns}",
        ]

        if high_mc:
            lines.append("\n*Tarefas mais citadas:*")
            for count, tid in high_mc:
                # Try to get title from last_snapshot
                snapshot = state.get("last_snapshot", {})
                title = snapshot.get(tid, {}).get("titulo", tid[:8])
                lines.append(f"  {title} — {count}x")

        return "\n".join(lines)

    def _cmd_next(self) -> str:
        """Top 3 priority tasks from state."""
        state_mgr = StateManager()
        state_path = state_mgr.state_path

        if not state_path.exists():
            return "Nenhum state encontrado. Rode `vera briefing` primeiro."

        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return "Erro ao ler state."

        snapshot = state.get("last_snapshot", {})
        mc = state.get("mention_counts", {})

        if not snapshot:
            return "Nenhuma tarefa no snapshot. Rode `vera briefing` primeiro."

        # Score tasks (simplified: deadline proximity + priority)
        from datetime import datetime

        hoje = datetime.now().strftime("%Y-%m-%d")
        scored = []

        for tid, task in snapshot.items():
            # Skip zombies and cooldowns
            task_mc = mc.get(tid, {})
            if task_mc.get("count", 0) >= 8:
                continue
            if task_mc.get("cooldown_until") and task_mc["cooldown_until"] > hoje:
                continue

            score = 0.0
            dl = task.get("deadline")
            if dl:
                if dl < hoje:
                    score += 100
                elif dl == hoje:
                    score += 80

            prio = (task.get("prioridade") or "").lower()
            if any(p in prio for p in ["alta", "high", "crítico"]):
                score += 30
            elif any(p in prio for p in ["média", "medium"]):
                score += 15

            mentions = task_mc.get("count", 0)
            score -= min(mentions * 3, 30)

            scored.append((score, task))

        scored.sort(reverse=True)
        top = scored[:3]

        if not top:
            return "Nenhuma tarefa prioritária no momento."

        lines = ["*Próximas prioridades:*\n"]
        for i, (score, task) in enumerate(top, 1):
            titulo = task.get("titulo", "?")
            dl = task.get("deadline", "")
            dl_str = f" (deadline: {dl})" if dl else ""
            prio = task.get("prioridade", "")
            prio_str = f" [{prio}]" if prio else ""
            lines.append(f"{i}. {titulo}{prio_str}{dl_str}")

        return "\n".join(lines)
