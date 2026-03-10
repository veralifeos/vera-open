"""News/Topic Monitoring Pack."""

from vera.research.packs.news.pack import NewsResearchPack
from vera.research.registry import registry

registry.register(NewsResearchPack)

__all__ = ["NewsResearchPack"]
