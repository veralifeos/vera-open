"""Domain — interface abstrata para domínios de vida."""

from abc import ABC, abstractmethod

from vera.backends.base import StorageBackend


class Domain(ABC):
    """Interface para domínios de vida.

    Cada domínio sabe buscar seus dados, analisar, e gerar
    contexto para o briefing.
    """

    def __init__(self, config: dict, backend: StorageBackend):
        self.config = config
        self.backend = backend

    @abstractmethod
    async def collect(self) -> dict:
        """Coleta dados do backend. Retorna dados brutos."""
        ...

    @abstractmethod
    def analyze(self, data: dict) -> dict:
        """Analisa dados coletados. Retorna insights."""
        ...

    @abstractmethod
    def context(self, data: dict, analysis: dict) -> str:
        """Gera texto de contexto para injetar no briefing."""
        ...
