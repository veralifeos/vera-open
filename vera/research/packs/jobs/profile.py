"""Carrega candidate_profile.yaml — single source of truth para scoring de vagas.

O profile fica em config/candidate_profile.yaml (gitignored) e contem
identidade, target_roles (exact/close/adjacent), stack, blockers e
scoring_weights. E lido por blockers.py e rule_scorer.py.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PROFILE_PATH = _REPO_ROOT / "config" / "candidate_profile.yaml"


_TARGET_COMPANIES_PATH = _REPO_ROOT / "config" / "target_companies.yaml"


@lru_cache(maxsize=1)
def load_profile(path: Path | None = None) -> dict:
    """Carrega e cacheia o perfil do candidato. Retorna {} se ausente."""
    p = path or _PROFILE_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_target_companies(path: Path | None = None) -> set[str]:
    """Carrega nomes das empresas-alvo (lowercased). Retorna set() se ausente."""
    p = path or _TARGET_COMPANIES_PATH
    if not p.exists():
        return set()
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {c["name"].strip().lower() for c in data.get("companies", [])}
