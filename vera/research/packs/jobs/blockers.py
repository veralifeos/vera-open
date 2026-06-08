"""Blockers — elimina vagas incompativeis antes de qualquer scoring.

Portado de vera-private/vera/scoring/blockers.py. Adaptado para operar
sobre ResearchItem em vez de dict bruto. Le config de blockers do
candidate_profile.yaml.

4 filtros:
  1. Titulos bloqueados (data analyst, media buyer, etc.)
  2. Stacks bloqueadas com excecoes (Pardot sem HubSpot, Salesforce sem GA4)
  3. Sinais de role (50% suporte, call center)
  4. Presencial fora de BH/MG
"""

from __future__ import annotations

from vera.research.base import ResearchItem
from vera.research.packs.jobs.profile import load_profile


def check_blockers(item: ResearchItem, profile: dict | None = None) -> dict | None:
    """
    Verifica se a vaga e bloqueada pelo perfil do candidato.

    Args:
        item: ResearchItem da vaga. Usa item.title, item.content e
              item.metadata (location, is_remote).
        profile: perfil carregado. Se None, carrega do YAML.

    Returns:
        None se nao bloqueada, ou dict {"blocked": True, "reason": str}.
    """
    if profile is None:
        profile = load_profile()

    blockers_cfg = profile.get("blockers", {})
    title = (item.title or "").lower()
    content = (item.content or "").lower()
    meta = item.metadata or {}
    location = (meta.get("location") or "").lower()
    is_remote = (
        bool(meta.get("is_remote") or meta.get("remote"))
        or "remote" in location
        or "remoto" in location
    )

    # 1. Bloqueio por titulo
    for blocked_title in blockers_cfg.get("titles", []):
        if blocked_title.lower() in title:
            return {"blocked": True, "reason": f"titulo bloqueado: '{blocked_title}'"}

    # 2. Bloqueio por stack com excecoes
    for stack_rule in blockers_cfg.get("stacks", []):
        stack_name = stack_rule["name"].lower()
        unless = [u.lower() for u in stack_rule.get("unless", [])]
        if stack_name in content:
            has_exception = any(exc in content for exc in unless)
            if not has_exception:
                return {"blocked": True, "reason": f"stack bloqueada: '{stack_name}' sem {unless}"}

    # 3. Bloqueio por sinais de role
    for signal in blockers_cfg.get("role_signals", []):
        if signal.lower() in content:
            return {"blocked": True, "reason": f"sinal de role bloqueado: '{signal}'"}

    # 4. Bloqueio por localizacao (presencial fora de BH/MG)
    if not is_remote and location:
        remote_exceptions = blockers_cfg.get("remote_exceptions", {})
        allowed_locations = [loc.lower() for loc in remote_exceptions.get("presential_allowed", [])]
        is_allowed_location = any(loc in location for loc in allowed_locations)
        if not is_allowed_location:
            return {"blocked": True, "reason": f"presencial fora de BH: '{location}'"}

    return None
