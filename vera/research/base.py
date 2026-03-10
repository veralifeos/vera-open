"""ResearchPack ABC + ResearchItem + ResearchResult dataclasses."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ResearchItem:
    """Um item encontrado por um pack."""

    id: str  # Hash unico (para dedup)
    title: str
    url: str
    source_name: str
    published: datetime | None
    content: str  # Texto completo ou resumo
    score: float = 0.0  # 0.0-1.0
    metadata: dict = field(default_factory=dict)
    topic: str | None = None


@dataclass
class ResearchResult:
    """Resultado consolidado de um ciclo de research."""

    pack_name: str
    items: list[ResearchItem]
    new_count: int
    total_checked: int
    sources_checked: int
    sources_failed: list[str]
    timestamp: datetime
    synthesis: str = ""


class ResearchPack(ABC):
    """Interface abstrata para Research Packs."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    async def collect(self, config: dict) -> list[ResearchItem]: ...

    @abstractmethod
    async def score(self, items: list[ResearchItem], config: dict) -> list[ResearchItem]: ...

    @abstractmethod
    def format_for_briefing(self, result: ResearchResult) -> str: ...

    def get_default_config(self) -> dict:
        """Retorna config default do pack."""
        return {}
