"""Financial/Investment Pack."""

from vera.research.packs.financial.pack import FinancialResearchPack
from vera.research.registry import registry

registry.register(FinancialResearchPack)

__all__ = ["FinancialResearchPack"]
