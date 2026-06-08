"""Testes para o filtro de blockers do jobs pack.

Portado de vera-private/tests/test_blockers.py, adaptado a ResearchItem.
Os casos cobrem os 4 filtros: titulo, stack com excecao, role signals,
presencial fora de BH.
"""

from datetime import datetime, timezone

from vera.research.base import ResearchItem
from vera.research.packs.jobs.blockers import check_blockers


def _item(title: str, content: str = "", **meta) -> ResearchItem:
    """Fabrica um ResearchItem minimo para teste."""
    return ResearchItem(
        id="test-id",
        title=title,
        url="https://example.com",
        source_name="test",
        published=datetime.now(timezone.utc),
        content=content,
        metadata=meta,
    )


# Profile em memoria para isolar testes do candidate_profile.yaml real
PROFILE = {
    "blockers": {
        "titles": [
            "analista de dados",
            "data analyst",
            "media buyer",
            "trafego pago",
        ],
        "stacks": [
            {"name": "pardot", "unless": ["hubspot"]},
            {"name": "salesforce", "unless": ["ga4", "google analytics"]},
        ],
        "role_signals": ["50% suporte", "call center"],
        "remote_exceptions": {
            "presential_allowed": ["belo horizonte", "bh", "minas gerais"]
        },
    }
}


# --- Bloqueio por titulo ---------------------------------------------------


def test_blocked_title_analista_dados():
    r = check_blockers(_item("Analista de Dados"), profile=PROFILE)
    assert r and r["blocked"]
    assert "titulo" in r["reason"]


def test_blocked_title_media_buyer():
    r = check_blockers(_item("Media Buyer Senior"), profile=PROFILE)
    assert r and r["blocked"]


def test_allowed_title_pmm():
    assert check_blockers(_item("Senior PMM"), profile=PROFILE) is None


def test_allowed_title_cro():
    assert check_blockers(_item("CRO Specialist"), profile=PROFILE) is None


# --- Bloqueio por stack ---------------------------------------------------


def test_blocked_stack_pardot_alone():
    r = check_blockers(
        _item("Marketing Ops", content="Experience with Pardot required"),
        profile=PROFILE,
    )
    assert r and r["blocked"]
    assert "pardot" in r["reason"]


def test_allowed_stack_pardot_with_hubspot():
    r = check_blockers(
        _item("Marketing Ops", content="Pardot e HubSpot"),
        profile=PROFILE,
    )
    assert r is None


def test_allowed_stack_salesforce_with_ga4():
    r = check_blockers(
        _item("RevOps", content="Salesforce, GA4, Looker"),
        profile=PROFILE,
    )
    assert r is None


# --- Bloqueio por role signals --------------------------------------------


def test_blocked_role_signal_call_center():
    r = check_blockers(
        _item("Customer Success", content="atendimento em call center"),
        profile=PROFILE,
    )
    assert r and r["blocked"]
    assert "call center" in r["reason"]


# --- Bloqueio por localizacao ---------------------------------------------


def test_blocked_presencial_sao_paulo():
    r = check_blockers(
        _item("CRO Manager", location="Sao Paulo, SP", is_remote=False),
        profile=PROFILE,
    )
    assert r and r["blocked"]
    assert "presencial" in r["reason"]


def test_allowed_presencial_bh():
    r = check_blockers(
        _item("CRO Manager", location="Belo Horizonte, MG", is_remote=False),
        profile=PROFILE,
    )
    assert r is None


def test_allowed_remote_via_metadata():
    r = check_blockers(
        _item("CRO Manager", location="Recife, PE", is_remote=True),
        profile=PROFILE,
    )
    assert r is None


def test_allowed_remote_via_location_string():
    r = check_blockers(
        _item("CRO Manager", location="remote"),
        profile=PROFILE,
    )
    assert r is None


# --- Pass-through ---------------------------------------------------------


def test_vanilla_job_passes():
    r = check_blockers(
        _item(
            "Growth Marketing Manager",
            content="HubSpot, GA4, B2B SaaS",
            location="remote",
            is_remote=True,
        ),
        profile=PROFILE,
    )
    assert r is None


def test_empty_profile_never_blocks():
    r = check_blockers(_item("Media Buyer"), profile={})
    assert r is None
