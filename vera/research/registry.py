"""PackRegistry — descoberta e carregamento de Research Packs."""

import importlib
import logging
from pathlib import Path

from vera.research.base import ResearchPack

logger = logging.getLogger(__name__)


class PackRegistry:
    """Registry de Research Packs com auto-discovery."""

    def __init__(self):
        self._packs: dict[str, type[ResearchPack]] = {}

    def register(self, pack_class: type[ResearchPack]) -> None:
        """Registra um pack."""
        # Instancia temporaria para pegar o name
        # (name e property, precisa de instancia ou inspecao)
        name = pack_class.__dict__.get("name", None)
        if name is None:
            # Tenta via instancia parcial — packs devem ter name como class-level
            try:
                # Para packs com name como class attribute (nao property)
                name = getattr(pack_class, "name", None)
                if callable(name):
                    name = None
            except Exception:
                name = None

        if name is None:
            name = pack_class.__name__.lower().replace("researchpack", "").replace("pack", "")

        self._packs[name] = pack_class
        logger.debug("Pack registrado: %s", name)

    def get(self, name: str) -> type[ResearchPack] | None:
        """Retorna classe do pack pelo nome."""
        return self._packs.get(name)

    def list_available(self) -> list[str]:
        """Lista nomes dos packs registrados."""
        return list(self._packs.keys())

    def discover(self) -> None:
        """Auto-discovery de packs em vera/research/packs/."""
        packs_dir = Path(__file__).parent / "packs"
        if not packs_dir.exists():
            return

        for pack_dir in packs_dir.iterdir():
            if not pack_dir.is_dir() or pack_dir.name.startswith("_"):
                continue

            module_name = f"vera.research.packs.{pack_dir.name}"
            try:
                importlib.import_module(module_name)
                logger.debug("Pack module loaded: %s", module_name)
            except ImportError as e:
                logger.debug("Pack '%s' nao carregado: %s", pack_dir.name, e)
            except Exception as e:
                logger.warning("Erro ao carregar pack '%s': %s", pack_dir.name, e)


# Singleton global
registry = PackRegistry()
