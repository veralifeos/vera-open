"""ObservationCollector — salva uma observação por briefing em state/observations.json."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path


class ObservationCollector:
    """Coleta e persiste observações de cada briefing."""

    STATE_PATH = Path("state/observations.json")
    MAX_DAYS = 90

    def _load(self) -> dict:
        self.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if self.STATE_PATH.exists():
            try:
                return json.loads(self.STATE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                pass
        return {"version": 1, "observations": [], "weekly_snapshots": []}

    def _save(self, data: dict) -> None:
        self.STATE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, data: dict) -> None:
        """Appends one observation. Keeps last 90 days only."""
        state = self._load()

        observation = {
            "date": date.today().isoformat(),
            "tasks_suggested": data.get("tasks_suggested", []),
            "tasks_completed": data.get("tasks_completed", []),
            "energy_score": data.get("energy_score", 0),
            "dia_num": data.get("dia_num", 0),
            "pack_results": data.get("pack_results", {}),
            "mention_counts_snapshot": data.get("mention_counts_snapshot", {}),
            "task_titles": data.get("task_titles", {}),  # {task_id: "título"}
        }

        state["observations"].append(observation)

        # Prune older than 90 days
        cutoff = (date.today() - timedelta(days=self.MAX_DAYS)).isoformat()
        state["observations"] = [
            o for o in state["observations"] if o.get("date", "") >= cutoff
        ]

        self._save(state)

    def load_observations(self) -> list[dict]:
        """Retorna lista de observações."""
        return self._load().get("observations", [])
