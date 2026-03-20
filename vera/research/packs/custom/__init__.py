"""Custom Research Pack — pack genérico configurável via YAML."""
from vera.research.packs.custom.pack import CustomResearchPack
from vera.research.registry import registry
registry.register(CustomResearchPack)
__all__ = ["CustomResearchPack"]
