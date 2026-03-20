"""BehaviorTracker — detecta sinais comportamentais a partir de observações."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass
class Signal:
    type: str
    value: Any
    evidence_count: int
    confidence: float


MIN_OBSERVATIONS = 5


class BehaviorTracker:
    """Detecta 5 sinais comportamentais a partir do histórico de observações."""

    def detect_signals(self, observations: list[dict]) -> list[Signal]:
        if len(observations) < MIN_OBSERVATIONS:
            return []

        signals: list[Signal] = []

        s = self._check_carga(observations)
        if s:
            signals.append(s)

        signals.extend(self._check_prioridade_real(observations))
        signals.extend(self._check_zona_morta(observations))
        signals.extend(self._check_pack_irrelevante(observations))

        s = self._check_ritmo(observations)
        if s:
            signals.append(s)

        return signals

    def _check_carga(self, observations: list[dict]) -> Signal | None:
        """avg energy_score < 5 in last 7 days AND 3+ briefings."""
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        recent = [o for o in observations if o.get("date", "") >= cutoff]

        if len(recent) < 3:
            return None

        scores = [o.get("energy_score", 10) for o in recent]
        avg = sum(scores) / len(scores)

        if avg < 5:
            return Signal(
                type="carga",
                value={"avg_energy": round(avg, 1), "days": len(recent)},
                evidence_count=len(recent),
                confidence=min(0.9, 0.6 + len(recent) * 0.05),
            )
        return None

    def _check_prioridade_real(self, observations: list[dict]) -> list[Signal]:
        """task_id in completed AND mention_count >= 4 in snapshot."""
        signals = []
        seen_tasks: set[str] = set()

        for obs in observations:
            completed = set(obs.get("tasks_completed", []))
            mc_snapshot = obs.get("mention_counts_snapshot", {})

            for tid in completed:
                if tid in seen_tasks:
                    continue
                count = mc_snapshot.get(tid, 0)
                if count >= 4:
                    seen_tasks.add(tid)
                    signals.append(Signal(
                        type="prioridade_real",
                        value={"task_id": tid, "mention_count": count},
                        evidence_count=count,
                        confidence=min(0.95, 0.7 + count * 0.03),
                    ))

        return signals[:3]  # max 3 per cycle

    def _check_zona_morta(self, observations: list[dict]) -> list[Signal]:
        """task_id with mention_count >= 7 across observations, never in completed."""
        all_completed: set[str] = set()
        task_max_mc: dict[str, int] = {}

        for obs in observations:
            all_completed.update(obs.get("tasks_completed", []))
            for tid, count in obs.get("mention_counts_snapshot", {}).items():
                if isinstance(count, (int, float)):
                    task_max_mc[tid] = max(task_max_mc.get(tid, 0), int(count))

        signals = []
        for tid, count in sorted(task_max_mc.items(), key=lambda x: -x[1]):
            if count >= 7 and tid not in all_completed:
                signals.append(Signal(
                    type="zona_morta",
                    value={"task_id": tid, "mention_count": count},
                    evidence_count=count,
                    confidence=min(0.9, 0.5 + count * 0.05),
                ))
            if len(signals) >= 3:
                break

        return signals

    def _check_pack_irrelevante(self, observations: list[dict]) -> list[Signal]:
        """Pack with 0 results in 5+ consecutive observations."""
        if len(observations) < 5:
            return []

        # Track consecutive zeros per pack
        pack_zeros: dict[str, int] = {}
        signals = []

        for obs in reversed(observations):  # most recent first
            pack_results = obs.get("pack_results", {})
            for pack_name, count in pack_results.items():
                if count == 0:
                    pack_zeros[pack_name] = pack_zeros.get(pack_name, 0) + 1
                else:
                    pack_zeros[pack_name] = 0  # reset streak

        for pack_name, zeros in pack_zeros.items():
            if zeros >= 5:
                signals.append(Signal(
                    type="pack_irrelevante",
                    value={"pack": pack_name, "consecutive_zeros": zeros},
                    evidence_count=zeros,
                    confidence=0.7,
                ))

        return signals

    def _check_ritmo(self, observations: list[dict]) -> Signal | None:
        """80%+ completions concentrated on same weekday across 14+ days."""
        if len(observations) < 14:
            return None

        cutoff = (date.today() - timedelta(days=14)).isoformat()
        recent = [o for o in observations if o.get("date", "") >= cutoff]

        day_completions: Counter[int] = Counter()
        total_completions = 0

        for obs in recent:
            completed = len(obs.get("tasks_completed", []))
            if completed > 0:
                dia = obs.get("dia_num", 0)
                day_completions[dia] += completed
                total_completions += completed

        if total_completions < 3:
            return None

        if day_completions:
            top_day, top_count = day_completions.most_common(1)[0]
            ratio = top_count / total_completions
            if ratio >= 0.8:
                dias = {0: "segunda", 1: "terça", 2: "quarta", 3: "quinta",
                        4: "sexta", 5: "sábado", 6: "domingo"}
                return Signal(
                    type="ritmo",
                    value={"weekday": top_day, "weekday_name": dias.get(top_day, "?"),
                           "ratio": round(ratio, 2)},
                    evidence_count=total_completions,
                    confidence=ratio,
                )
        return None
