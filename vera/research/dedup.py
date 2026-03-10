"""DedupEngine — deduplicacao TTL-based com persistencia JSON."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from vera.research.base import ResearchItem

logger = logging.getLogger(__name__)


class DedupEngine:
    """Deduplicacao de items com TTL configuravel."""

    def __init__(self, state_path: Path, default_ttl_days: int = 30):
        """
        Args:
            state_path: Caminho para o arquivo JSON de estado (ex: state/dedup/news.json).
            default_ttl_days: TTL padrao em dias para items vistos.
        """
        self.state_path = state_path
        self.default_ttl_days = default_ttl_days
        self._seen: dict[str, str] = {}  # id -> expiry ISO string
        self.load()

    @staticmethod
    def compute_id(title: str, url: str, source: str) -> str:
        """Hash MD5 de titulo normalizado (lowercase, strip) + URL."""
        normalized = f"{title.lower().strip()}|{url.strip()}|{source}"
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def is_seen(self, item_id: str) -> bool:
        """Verifica se item ja foi visto e nao expirou."""
        expiry_str = self._seen.get(item_id)
        if not expiry_str:
            return False

        try:
            expiry = datetime.fromisoformat(expiry_str)
            if datetime.now(timezone.utc) > expiry:
                # Expirou — remove
                del self._seen[item_id]
                return False
            return True
        except (ValueError, TypeError):
            return False

    def mark_seen(self, item_id: str, ttl_days: int | None = None) -> None:
        """Marca item como visto com TTL."""
        from datetime import timedelta

        ttl = ttl_days if ttl_days is not None else self.default_ttl_days
        expiry = datetime.now(timezone.utc) + timedelta(days=ttl)
        self._seen[item_id] = expiry.isoformat()

    def filter_new(self, items: list[ResearchItem]) -> list[ResearchItem]:
        """Filtra items novos (nao vistos ou expirados)."""
        new_items = []
        for item in items:
            if not self.is_seen(item.id):
                new_items.append(item)
        return new_items

    def mark_items(self, items: list[ResearchItem], ttl_days: int | None = None) -> None:
        """Marca multiplos items como vistos."""
        for item in items:
            self.mark_seen(item.id, ttl_days)

    def cleanup_expired(self) -> int:
        """Remove entries expiradas. Retorna quantidade removida."""
        now = datetime.now(timezone.utc)
        expired = []
        for item_id, expiry_str in self._seen.items():
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if now > expiry:
                    expired.append(item_id)
            except (ValueError, TypeError):
                expired.append(item_id)

        for item_id in expired:
            del self._seen[item_id]

        if expired:
            logger.debug("Dedup cleanup: %d expired entries removed", len(expired))
        return len(expired)

    def load(self) -> None:
        """Carrega estado do disco."""
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                self._seen = data.get("seen", {})
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Erro ao carregar dedup state: %s", e)
                self._seen = {}
        else:
            self._seen = {}

    def save(self) -> None:
        """Salva estado no disco."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"seen": self._seen}
        self.state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @property
    def seen_count(self) -> int:
        """Quantidade de items no cache."""
        return len(self._seen)
