"""Source health tracking — monitora fontes de dados que retornam 0 resultados."""

import json
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = _REPO_ROOT / "state" / "source_health.json"


class SourceHealthTracker:
    """Rastreia fontes de dados com zeros consecutivos."""

    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_PATH

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(self, source_name: str, result_count: int) -> None:
        """Registra resultado de uma fonte. Reseta contador se > 0."""
        data = self._load()
        now = datetime.now(timezone.utc).isoformat()

        if result_count > 0:
            data[source_name] = {
                "consecutive_zeros": 0,
                "last_count": result_count,
                "last_updated": now,
            }
        else:
            entry = data.get(
                source_name,
                {
                    "consecutive_zeros": 0,
                    "last_count": 0,
                },
            )
            entry["consecutive_zeros"] = entry.get("consecutive_zeros", 0) + 1
            entry["last_count"] = 0
            entry["last_updated"] = now
            data[source_name] = entry

        self._save(data)

    def get_alerts(self, threshold: int = 3) -> list[str]:
        """Retorna fontes com N+ zeros consecutivos."""
        data = self._load()
        alerts = []
        for source, info in data.items():
            zeros = info.get("consecutive_zeros", 0)
            if zeros >= threshold:
                alerts.append(source)
        return sorted(alerts)

    def format_for_briefing(self, threshold: int = 3) -> str:
        """Retorna texto formatado para injetar no briefing, ou '' se sem alertas."""
        alerts = self.get_alerts(threshold)
        if not alerts:
            return ""

        data = self._load()
        lines = ["=== ALERTAS DO SISTEMA ==="]
        for source in alerts:
            zeros = data[source].get("consecutive_zeros", 0)
            lines.append(f'Fonte "{source}" sem resultados ha {zeros} execucoes consecutivas')

        return "\n".join(lines)
