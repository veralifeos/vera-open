"""Registry de domínios de vida."""

from vera.domains.base import Domain

__all__ = ["Domain"]

# Mapa de domínios disponíveis — usado pelo config loader
DOMAIN_REGISTRY: dict[str, type[Domain]] = {}


def register_domain(name: str, cls: type[Domain]) -> None:
    """Registra um domínio no registry."""
    DOMAIN_REGISTRY[name] = cls


def get_domain(name: str) -> type[Domain] | None:
    """Retorna a classe de domínio pelo nome."""
    return DOMAIN_REGISTRY.get(name)


def _auto_register() -> None:
    """Auto-registra domínios built-in."""
    from vera.domains.contacts import ContactsDomain
    from vera.domains.pipeline import PipelineDomain
    from vera.domains.tasks import TasksDomain

    register_domain("tasks", TasksDomain)
    register_domain("pipeline", PipelineDomain)
    register_domain("contacts", ContactsDomain)


_auto_register()
