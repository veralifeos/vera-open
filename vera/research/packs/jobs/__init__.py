"""Job Search Pack."""

from vera.research.packs.jobs.pack import JobSearchPack
from vera.research.registry import registry

registry.register(JobSearchPack)

__all__ = ["JobSearchPack"]
