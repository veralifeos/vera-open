"""Testes do rule scorer 14-dim do jobs pack.

Portado de vera-private/tests/test_rule_scorer.py, adaptado a ResearchItem.
Cobre: 3-tier title, CRO keywords, B2B SaaS, stack 2+, remote, CLT/USD,
CLT explicito, Brasil location, PT-BR, beneficios, setor, easy apply,
pipeline pequeno, referral, target company, CAP em 10.
"""

from datetime import datetime, timezone
from unittest.mock import patch

from vera.research.base import ResearchItem
from vera.research.packs.jobs.scorer import JobScorer
from vera.research.scoring import ScoringEngine


# Profile que reproduz o candidate_profile.yaml do Fernando
_PROFILE = {
    "target_roles": {
        "exact": ["CRO Specialist", "CRO Manager", "CRO Expert", "Especialista em CRO"],
        "close": ["PMM", "Growth Marketing Manager", "Growth Lead", "Performance Marketing"],
        "adjacent": ["RevOps", "Creative Lead", "Marketing Operations"],
    },
    "stack": {"strong": ["GA4", "HubSpot", "Microsoft Clarity", "Figma", "GTM"]},
    "sectors_preferred": ["fintech", "edtech", "b2b saas"],
    "scoring_weights": {
        "title_exact": 3.0,
        "title_close": 2.0,
        "title_adjacent": 1.0,
        "cro_keywords": 0.5,
        "b2b_saas": 1.5,
        "stack_match_2plus": 1.0,
        "remote": 1.0,
        "clt_or_usd": 0.5,
        "clt_explicit": 1.0,
        "brasil_location": 0.5,
        "portugues": 0.3,
        "beneficios": 0.3,
        "preferred_sector": 0.5,
        "easy_apply": 0.3,
        "small_pipeline": 0.2,
        "referral": 0.5,
        "target_company": 2.0,
    },
    "blockers": {},  # Sem blockers nesses testes
}


def _item(title: str, content: str = "", **meta) -> ResearchItem:
    return ResearchItem(
        id=f"id-{title}",
        title=title,
        url="https://example.com",
        source_name="test",
        published=datetime.now(timezone.utc),
        content=content,
        metadata=meta,
    )


def _score(item: ResearchItem, target_companies: set[str] | None = None) -> float:
    """Helper — roda scorer com _PROFILE e target_companies opcional."""
    scorer = JobScorer(ScoringEngine())
    with patch(
        "vera.research.packs.jobs.scorer.load_profile", return_value=_PROFILE
    ), patch(
        "vera.research.packs.jobs.scorer.load_target_companies",
        return_value=target_companies or set(),
    ):
        return scorer.score_rules(item, {})


# --- Title 3-tier --------------------------------------------------------


def test_title_exact_cro():
    # CRO Manager + remote = 3.0 + 1.0 = 4.0/10 = 0.4
    score = _score(_item("CRO Manager at Foo", location="remote"))
    assert score == 0.4


def test_title_close_pmm():
    # PMM + remote = 2.0 + 1.0 = 3.0/10 = 0.3
    score = _score(_item("Senior PMM", location="remote"))
    assert score == 0.3


def test_title_adjacent_revops():
    # RevOps + remote = 1.0 + 1.0 = 2.0/10 = 0.2
    score = _score(_item("RevOps Analyst", location="remote"))
    assert score == 0.2


def test_title_tiers_mutually_exclusive():
    # Titulo tem CRO (exact) e RevOps (adjacent) — so o exact conta
    item = _item("CRO Manager / RevOps", location="remote")
    # Exact 3.0 + remote 1.0 = 4.0/10
    assert _score(item) == 0.4


def test_title_no_match():
    # Nenhum target_role na title, so remote
    score = _score(_item("Backend Engineer", location="remote"))
    assert score == 0.1  # apenas remote 1.0/10


# --- CRO keywords bonus --------------------------------------------------


def test_cro_keywords_bonus_when_not_exact():
    # close title "PMM" + CRO keyword → 2.0 + 0.5 = 2.5
    item = _item("Senior PMM", content="conversion rate optimization")
    # close 2.0 + cro 0.5 = 2.5/10 = 0.25
    assert _score(item) == 0.25


def test_cro_keywords_suppressed_when_exact():
    # exact title "CRO Manager" + CRO keyword → so exact (nao double-count)
    item = _item("CRO Manager", content="conversion rate optimization")
    # exact 3.0 only (sem remote) = 3.0/10 = 0.3
    assert _score(item) == 0.3


# --- B2B SaaS ------------------------------------------------------------


def test_b2b_saas_literal():
    # "b2b saas" e tambem sector preferido, por isso +sector tambem
    item = _item("PMM", content="B2B SaaS startup")
    # close 2.0 + b2b 1.5 + sector 0.5 = 4.0/10
    assert _score(item) == 0.4


def test_b2b_saas_synonym_enterprise_software():
    item = _item("PMM", content="Enterprise software company")
    # close 2.0 + b2b 1.5 = 3.5/10
    assert _score(item) == 0.35


def test_b2b_saas_from_target_company():
    # Target company implica b2b_saas (mesmo sem literal)
    item = _item("PMM", content="")
    item.metadata["company"] = "RD Station"
    # close 2.0 + b2b 1.5 + target 2.0 = 5.5/10
    assert _score(item, target_companies={"rd station"}) == 0.55


# --- Stack 2+ matches ----------------------------------------------------


def test_stack_2plus_fires():
    item = _item("PMM", content="requires GA4, HubSpot and Figma")
    # close 2.0 + stack 1.0 = 3.0/10
    assert _score(item) == 0.3


def test_stack_single_match_no_bonus():
    item = _item("PMM", content="requires GA4 only")
    # close 2.0 + nada (1 stack so) = 2.0/10
    assert _score(item) == 0.2


# --- Remote --------------------------------------------------------------


def test_remote_via_is_remote_flag():
    item = _item("Backend", is_remote=True)
    assert _score(item) == 0.1  # remote 1.0/10


def test_remote_via_location_string():
    item = _item("Backend", location="Remote - Anywhere")
    assert _score(item) == 0.1


# --- CLT Brasil bundle ---------------------------------------------------


def test_clt_explicit_and_brasil():
    item = _item(
        "CRO Manager",
        content="vaga CLT carteira assinada com beneficios: vale alimentacao e plano de saude",
        location="Belo Horizonte, MG",
    )
    # exact 3.0 + clt_explicit 1.0 + brasil 0.5 + portugues 0.3 + beneficios 0.3 = 5.1/10
    assert _score(item) >= 0.5


def test_usd_currency():
    item = _item("PMM", salary_currency="USD")
    # close 2.0 + clt_or_usd 0.5 = 2.5/10
    assert _score(item) == 0.25


# --- Setor preferido -----------------------------------------------------


def test_preferred_sector():
    item = _item("PMM", content="fintech startup in series B")
    # close 2.0 + sector 0.5 = 2.5/10
    assert _score(item) == 0.25


# --- Metadata bonuses ----------------------------------------------------


def test_easy_apply():
    item = _item("PMM", easy_apply=True)
    # close 2.0 + easy 0.3 = 2.3/10
    assert abs(_score(item) - 0.23) < 0.01


def test_small_pipeline():
    item = _item("PMM", applicants=10)
    # close 2.0 + small 0.2 = 2.2/10
    assert abs(_score(item) - 0.22) < 0.01


def test_referral():
    item = _item("PMM", is_referral=True)
    # close 2.0 + referral 0.5 = 2.5/10
    assert _score(item) == 0.25


# --- Cap em 10 -----------------------------------------------------------


def test_score_caps_at_one():
    # Vaga perfeita: exact + target + tudo = >10 → cap em 10 → 1.0
    item = _item(
        "CRO Manager",
        content=(
            "B2B SaaS fintech, requires GA4 HubSpot Figma GTM, "
            "vaga CLT carteira assinada, vale alimentacao plano de saude PLR, "
            "requisitos beneficios experiencia"
        ),
        location="remote Brasil",
        salary_currency="USD",
        contract_type="CLT",
        is_remote=True,
        easy_apply=True,
        applicants=5,
        is_referral=True,
        company="RD Station",
    )
    assert _score(item, target_companies={"rd station"}) == 1.0


# --- Fallback legacy quando profile ausente ------------------------------


def test_no_profile_falls_back_to_legacy():
    scorer = JobScorer(ScoringEngine())
    item = _item("Growth Lead", content="Growth marketing", location="remote")
    item.metadata["remote"] = True
    # Com profile vazio, cai no legacy que aceita criteria
    with patch("vera.research.packs.jobs.scorer.load_profile", return_value={}):
        score = scorer.score_rules(
            item,
            {"keywords": ["growth"], "location": "remote", "stack": ["GA4"]},
        )
    # Legacy retorna algo > 0 (nao e o zero do 14-dim sem title match)
    assert score > 0.0
