"""Source ABC — interface abstrata para fontes de dados."""

from abc import ABC, abstractmethod

from vera.research.base import ResearchItem


class Source(ABC):
    """Interface para fontes de dados de research."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def fetch(self, config: dict) -> list[dict]: ...

    @abstractmethod
    def parse(self, raw_item: dict) -> ResearchItem | None: ...
