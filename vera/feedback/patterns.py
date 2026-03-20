"""PatternEngine — converte sinais em inferências (rule-based, sem LLM)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

from vera.feedback.tracker import Signal


@dataclass
class Inference:
    id: str
    type: str
    text: str
    created_at: str
    expires_at: str
    evidence_count: int


EXPIRY_DAYS = 30


class PatternEngine:
    """Converte sinais comportamentais em inferências textuais."""

    def generate_inferences(self, signals: list[Signal]) -> list[Inference]:
        inferences: list[Inference] = []
        today = date.today().isoformat()
        expires = (date.today() + timedelta(days=EXPIRY_DAYS)).isoformat()

        for signal in signals:
            inference = self._signal_to_inference(signal, today, expires)
            if inference:
                inferences.append(inference)

        return inferences

    def _signal_to_inference(
        self, signal: Signal, today: str, expires: str
    ) -> Inference | None:
        if signal.type == "carga":
            avg = signal.value.get("avg_energy", 0)
            days = signal.value.get("days", 7)
            text = (
                f"Reduzir carga: energia média {avg:.1f}/10 nas últimas "
                f"{days} semanas. Vera vai sugerir no máximo 2 prioridades "
                f"até normalizar."
            )
            return self._make_inference(
                "carga", text, today, expires, signal.evidence_count,
                dedup_key="carga|active",
            )

        if signal.type == "prioridade_real":
            tid = signal.value.get("task_id", "?")
            title = signal.value.get("title", tid)
            count = signal.value.get("mention_count", 0)
            text = (
                f"Prioridade real detectada: '{title}' foi concluída após "
                f"{count} menções. Adicionado ao scoring."
            )
            return self._make_inference(
                "prioridade_real", text, today, expires, signal.evidence_count,
                dedup_key=f"prioridade_real|{tid}",
            )

        if signal.type == "zona_morta":
            tid = signal.value.get("task_id", "?")
            title = signal.value.get("title", tid)
            count = signal.value.get("mention_count", 0)
            text = (
                f"Parar de mencionar: '{title}' apareceu {count}x sem ação. "
                f"— remova esta linha se discordar"
            )
            return self._make_inference(
                "zona_morta", text, today, expires, signal.evidence_count,
                dedup_key=f"zona_morta|{tid}",
            )

        # v1: skip ritmo and pack_irrelevante
        return None

    @staticmethod
    def _make_inference(
        inf_type: str, text: str, created_at: str, expires_at: str, evidence_count: int,
        dedup_key: str | None = None,
    ) -> Inference:
        # Dedup by type+target (stable across runs), not by date
        key = dedup_key or f"{inf_type}|{text}"
        inf_id = hashlib.md5(key.encode()).hexdigest()[:12]
        return Inference(
            id=inf_id,
            type=inf_type,
            text=text,
            created_at=created_at,
            expires_at=expires_at,
            evidence_count=evidence_count,
        )
