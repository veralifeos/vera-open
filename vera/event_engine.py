"""Event Engine — eventos especiais de personalidade da Vera.

Gerencia até 2 eventos por semana:
- [PRAISE]  reconhecimento factual de progresso real
- [IRONY]   ironia seca sobre padrão operacional específico

Arquitetura:
  EventEngine.evaluate() -> EventResult | None
  EventResult injeta uma linha no contexto do briefing via [PRAISE]: ou [IRONY]:
  O LLM lê o sinal e integra naturalmente no texto (instruído em personas.py).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Literal


# --- Types -------------------------------------------------------------------


@dataclass
class EventResult:
    type: Literal["praise", "irony"]
    signal: str          # linha injetada no contexto
    reason: str          # log interno
    trigger_id: str      # hash para evitar repetição


@dataclass
class EventState:
    events_this_week: int = 0
    last_event_date: str = ""
    last_event_type: str = ""
    week_start: str = ""
    used_trigger_ids: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "EventState":
        return cls(
            events_this_week=data.get("events_this_week", 0),
            last_event_date=data.get("last_event_date", ""),
            last_event_type=data.get("last_event_type", ""),
            week_start=data.get("week_start", ""),
            used_trigger_ids=data.get("used_trigger_ids", []),
        )

    def to_dict(self) -> dict:
        return {
            "events_this_week": self.events_this_week,
            "last_event_date": self.last_event_date,
            "last_event_type": self.last_event_type,
            "week_start": self.week_start,
            "used_trigger_ids": self.used_trigger_ids,
        }


# --- Engine ------------------------------------------------------------------


class EventEngine:
    """Decide se um evento especial deve ocorrer no briefing de hoje."""

    STATE_PATH = Path("state/events.json")
    MAX_PER_WEEK = 2
    MIN_DAYS_BETWEEN = 2

    def __init__(self) -> None:
        self._state = self._load_state()

    def evaluate(self, context: dict) -> "EventResult | None":
        today = date.today().isoformat()
        self._maybe_reset_week(today)

        if not self._can_fire(today, context):
            return None

        result = self._check_praise(context, today)
        if result:
            return result

        return self._check_irony(context, today)

    def mark_used(self, result: "EventResult") -> None:
        today = date.today().isoformat()
        self._state.events_this_week += 1
        self._state.last_event_date = today
        self._state.last_event_type = result.type
        if result.trigger_id not in self._state.used_trigger_ids:
            self._state.used_trigger_ids.append(result.trigger_id)
        self._state.used_trigger_ids = self._state.used_trigger_ids[-50:]
        self._save_state()

    # -- Guards ---------------------------------------------------------------

    def _can_fire(self, today: str, context: dict) -> bool:
        if self._state.events_this_week >= self.MAX_PER_WEEK:
            return False
        if self._state.last_event_date:
            last = date.fromisoformat(self._state.last_event_date)
            if (date.fromisoformat(today) - last).days < self.MIN_DAYS_BETWEEN:
                return False
        if context.get("avg_task_score", 0) > 80:
            return False
        if context.get("energy_score", 10) < 4:
            return False
        return True

    # -- Praise ---------------------------------------------------------------

    def _check_praise(self, context: dict, today: str) -> "EventResult | None":
        # Zombie resolvido voluntariamente
        for z in context.get("resolved_zombies", []):
            tid = self._trigger_id("praise_zombie", z.get("titulo", ""))
            if tid not in self._state.used_trigger_ids:
                count = z.get("count", "?")
                signal = (
                    f"[PRAISE]: {z['titulo']} estava na lista há "
                    f"{count} semanas e foi concluída. Isso não é trivial."
                )
                return EventResult("praise", signal, f"zombie resolvido: {z['titulo']}", tid)

        # 3+ concluídas e backlog caiu
        completed = context.get("completed_count", 0)
        delta = context.get("backlog_delta", 0)
        if completed >= 3 and delta < 0:
            tid = self._trigger_id("praise_bulk", today[:7])
            if tid not in self._state.used_trigger_ids:
                signal = (
                    f"[PRAISE]: {completed} tarefas fechadas. "
                    f"Backlog caiu {abs(delta)} itens. Registro feito."
                )
                return EventResult("praise", signal, f"{completed} concluídas", tid)

        # Tarefa high-mention concluída
        for t in context.get("high_mention_completed", []):
            tid = self._trigger_id("praise_high_mention", t.get("titulo", ""))
            if tid not in self._state.used_trigger_ids:
                count = t.get("count", 4)
                signal = (
                    f"[PRAISE]: {t['titulo']} apareceu aqui {count} vezes "
                    f"e finalmente saiu da lista. Isso tem nome."
                )
                return EventResult("praise", signal, f"high-mention: {t['titulo']} ({count}x)", tid)

        # Pipeline avançou
        pa = context.get("pipeline_advance")
        if pa:
            tid = self._trigger_id("praise_pipeline", pa.get("titulo", ""))
            if tid not in self._state.used_trigger_ids:
                signal = (
                    f"[PRAISE]: {pa['titulo']} avançou para "
                    f"{pa.get('novo_status', 'próxima fase')}. Pipeline se moveu."
                )
                return EventResult("praise", signal, f"pipeline: {pa['titulo']}", tid)

        return None

    # -- Irony ----------------------------------------------------------------

    def _check_irony(self, context: dict, today: str) -> "EventResult | None":
        # Tarefa crônica (5+ menções)
        for t in context.get("chronic_tasks", []):
            count = t.get("count", 5)
            tid = self._trigger_id("irony_chronic", t.get("titulo", ""), count // 2)
            if tid not in self._state.used_trigger_ids:
                weeks = round(count / 5)
                time_str = f"{weeks} semana{'s' if weeks > 1 else ''}" if weeks >= 1 else f"{count} briefings"
                signal = (
                    f"[IRONY]: {t['titulo']} está aqui há {time_str}. "
                    f"A essa altura ela já faz parte da mobília."
                )
                return EventResult("irony", signal, f"crônica: {t['titulo']} ({count}x)", tid)

        # Deadline venceu ontem
        for t in context.get("missed_deadlines_yesterday", []):
            tid = self._trigger_id("irony_missed", t.get("titulo", ""), today)
            if tid not in self._state.used_trigger_ids:
                signal = (
                    f"[IRONY]: {t['titulo']} tinha deadline ontem. "
                    f"Ainda aqui. Só registrando."
                )
                return EventResult("irony", signal, f"deadline perdido: {t['titulo']}", tid)

        # Follow-up parado 14+ dias
        for t in context.get("stale_followups", []):
            tid = self._trigger_id("irony_followup", t.get("titulo", ""))
            if tid not in self._state.used_trigger_ids:
                days = t.get("days_stale", 14)
                signal = (
                    f"[IRONY]: {t['titulo']}: {days} dias sem resposta. "
                    f"Pergunto uma vez: espera ou arquiva?"
                )
                return EventResult("irony", signal, f"follow-up parado: {t['titulo']} ({days}d)", tid)

        # Segunda com zero concluídas na semana anterior
        if context.get("weekday_num") == 0 and context.get("last_week_completed", 1) == 0:
            tid = self._trigger_id("irony_zero_week", today[:7])
            if tid not in self._state.used_trigger_ids:
                signal = (
                    "[IRONY]: Semana passada: zero tarefas concluídas. "
                    "Semana nova, lista intacta. Vamos ver como termina."
                )
                return EventResult("irony", signal, "zero completions last week", tid)

        # Tarefa "urgente" há 3+ semanas
        for t in context.get("stale_urgent_tasks", []):
            tid = self._trigger_id("irony_urgente", t.get("titulo", ""))
            if tid not in self._state.used_trigger_ids:
                count = t.get("count", 15)
                signal = (
                    f"[IRONY]: {t['titulo']} está marcada como urgente há "
                    f"{round(count / 5)} semanas. "
                    f"Talvez seja hora de renegociar o que 'urgente' significa aqui."
                )
                return EventResult("irony", signal, f"urgente crônico: {t['titulo']}", tid)

        return None

    # -- State ----------------------------------------------------------------

    def _maybe_reset_week(self, today: str) -> None:
        today_date = date.fromisoformat(today)
        monday = today_date - timedelta(days=today_date.weekday())
        monday_str = monday.isoformat()
        if self._state.week_start != monday_str:
            self._state.events_this_week = 0
            self._state.week_start = monday_str
            self._save_state()

    def _load_state(self) -> EventState:
        self.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if self.STATE_PATH.exists():
            try:
                data = json.loads(self.STATE_PATH.read_text(encoding="utf-8"))
                return EventState.from_dict(data)
            except Exception:
                pass
        return EventState()

    def _save_state(self) -> None:
        self.STATE_PATH.write_text(
            json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _trigger_id(*parts) -> str:
        key = "|".join(str(p) for p in parts)
        return hashlib.md5(key.encode()).hexdigest()[:12]


# --- Context builder ---------------------------------------------------------


def build_event_context(
    tarefas: list,
    completed_tasks: list,
    mention_counts: dict,
    state: dict,
    delta: dict,
    domain_analyses: dict,
    weekday_num: int,
) -> dict:
    """Constrói o dicionário de contexto para EventEngine.evaluate()."""
    from datetime import datetime, timedelta as _td

    hoje = datetime.now().strftime("%Y-%m-%d")
    ontem = (datetime.now() - _td(days=1)).strftime("%Y-%m-%d")

    completed_ids = {t["id"] for t in completed_tasks}
    resolved_zombies = []
    high_mention_completed = []

    for tid, mc in mention_counts.items():
        if tid in completed_ids:
            count = mc.get("count", 0)
            titulo = mc.get("titulo", tid)
            if count >= 7:
                resolved_zombies.append({"id": tid, "titulo": titulo, "count": count})
            elif count >= 4:
                high_mention_completed.append({"id": tid, "titulo": titulo, "count": count})

    backlog_delta = len(completed_tasks) - len(delta.get("novas", []))

    chronic_tasks = []
    stale_urgent = []
    for t in tarefas:
        tid = t["id"]
        count = mention_counts.get(tid, {}).get("count", 0)
        if count >= 5:
            chronic_tasks.append({**t, "count": count})
        prio = (t.get("prioridade") or "").lower()
        if count >= 15 and any(p in prio for p in ["alta", "high", "urgent", "crítico"]):
            stale_urgent.append({**t, "count": count})

    missed_deadlines_yesterday = [t for t in tarefas if t.get("deadline") == ontem]

    stale_followups = []
    pipeline_analysis = domain_analyses.get("pipeline", {})
    for item in pipeline_analysis.get("aguardando", []):
        days = item.get("days_waiting", 0)
        if days >= 14:
            stale_followups.append({**item, "days_stale": days})

    pipeline_advance = None
    for item in pipeline_analysis.get("avancos_recentes", []):
        novo = (item.get("status") or "").lower()
        if any(s in novo for s in ["entrevista", "proposta", "teste", "aprovado"]):
            pipeline_advance = item
            break

    check_analysis = domain_analyses.get("check", {})
    energy_score = check_analysis.get("energia", 10) if check_analysis else 10

    scores = [t.get("_score", 0) for t in tarefas]
    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "resolved_zombies": sorted(resolved_zombies, key=lambda x: -x["count"])[:3],
        "high_mention_completed": sorted(high_mention_completed, key=lambda x: -x["count"])[:3],
        "completed_count": len(completed_tasks),
        "backlog_delta": backlog_delta,
        "pipeline_advance": pipeline_advance,
        "chronic_tasks": sorted(chronic_tasks, key=lambda x: -x["count"])[:3],
        "missed_deadlines_yesterday": missed_deadlines_yesterday[:3],
        "stale_followups": sorted(stale_followups, key=lambda x: -x.get("days_stale", 0))[:3],
        "stale_urgent_tasks": sorted(stale_urgent, key=lambda x: -x["count"])[:3],
        "energy_score": energy_score,
        "last_week_completed": len(completed_tasks) if weekday_num == 0 else 1,
        "avg_task_score": avg_score,
        "weekday_num": weekday_num,
    }
