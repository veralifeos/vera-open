"""Testes do modulo astro pessoal."""

from unittest.mock import patch

import pytest

from vera.personal import astro


def test_lon_to_sign_conhecido():
    # Sol a 282.73 deg -> Capricornio 12.7
    signo, grau = astro._lon_to_sign(282.73)
    assert signo == "Capricornio"
    assert abs(grau - 12.7) < 0.1


def test_lon_to_sign_wrap_around():
    signo, grau = astro._lon_to_sign(360.0)
    assert signo == "Aries"
    assert grau == 0.0


@pytest.mark.skipif(
    pytest.importorskip("swisseph", reason="pyswisseph nao instalado") is None,
    reason="pyswisseph nao disponivel",
)
def test_calcular_natal_fernando():
    """Valida posicao do Sol natal do Fernando: Capricornio ~12-13 graus."""
    natal = astro.calcular_natal()
    assert "Sol" in natal
    assert natal["Sol"]["signo"] == "Capricornio"
    assert 10 <= natal["Sol"]["grau"] <= 15


def test_aspectos_conjuncao_detectada():
    # Transito no mesmo grau do natal = conjuncao orbe 0
    transitos = {"Marte": {"longitude": 100.0, "signo": "Cancer", "grau": 10.0}}
    natal = {"Sol": {"longitude": 100.0, "signo": "Cancer", "grau": 10.0}}
    aspectos = astro.calcular_aspectos(transitos, natal)
    assert len(aspectos) == 1
    assert aspectos[0]["aspecto"] == "conjuncao"
    assert aspectos[0]["orbe"] == 0.0


def test_aspectos_oposicao_detectada():
    # 180 graus = oposicao
    transitos = {"Marte": {"longitude": 100.0, "signo": "Cancer", "grau": 10.0}}
    natal = {"Sol": {"longitude": 280.0, "signo": "Capricornio", "grau": 10.0}}
    aspectos = astro.calcular_aspectos(transitos, natal)
    assert any(a["aspecto"] == "oposicao" for a in aspectos)


def test_aspectos_fora_de_orbe_ignorado():
    transitos = {"Marte": {"longitude": 100.0, "signo": "Cancer", "grau": 10.0}}
    natal = {"Sol": {"longitude": 150.0, "signo": "Leao", "grau": 0.0}}  # 50 deg
    aspectos = astro.calcular_aspectos(transitos, natal)
    # 50 deg nao encaixa em nenhum aspecto com orbe 4
    assert all(a["aspecto"] != "conjuncao" for a in aspectos)


# --- Notion parser -------------------------------------------------------


def test_parse_natal_from_notion_blocks():
    """Parser de mapa natal deve extrair de blocks de texto plausiveis."""
    fake_blocks = [
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Sol: Capricornio 12.7"}]}},
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Lua em Escorpiao 15.2"}]}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"plain_text": "Ascendente: Libra 20.9"}]}},
    ]
    with patch.object(astro, "fetch_notion_page_blocks", return_value=fake_blocks), \
         patch.object(astro, "NOTION_PAGE_NATAL", "fake_id"):
        natal = astro.load_natal_from_notion("fake_id")
    assert natal is not None
    assert natal["Sol"]["signo"] == "Capricornio"
    assert natal["Lua"]["signo"] == "Escorpiao"
    assert natal["ASC"]["signo"] == "Libra"


def test_parse_natal_insufficient_returns_none():
    """Se menos de 3 planetas parseaveis, retorna None (fallback)."""
    fake_blocks = [
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Sol em Capricornio 12"}]}},
    ]
    with patch.object(astro, "fetch_notion_page_blocks", return_value=fake_blocks):
        natal = astro.load_natal_from_notion("fake_id")
    assert natal is None


def test_parse_natal_no_page_id_returns_none():
    with patch.object(astro, "NOTION_PAGE_NATAL", ""):
        natal = astro.load_natal_from_notion(None)
    assert natal is None


# --- Fallback chain ------------------------------------------------------


def test_load_or_compute_natal_uses_notion_first():
    fake_natal = {
        "Sol": {"longitude": 282.0, "signo": "Capricornio", "grau": 12.0},
        "Lua": {"longitude": 225.0, "signo": "Escorpiao", "grau": 15.0},
        "ASC": {"longitude": 200.0, "signo": "Libra", "grau": 20.0},
    }
    with patch.object(astro, "load_natal_from_notion", return_value=fake_natal):
        natal = astro.load_or_compute_natal()
    assert natal == fake_natal


def test_load_or_compute_natal_falls_back_to_json(tmp_path, monkeypatch):
    import json
    fake_json = {
        "Sol": {"longitude": 282.73, "signo": "Capricornio", "grau": 12.7},
    }
    path = tmp_path / "natal_chart.json"
    path.write_text(json.dumps(fake_json), encoding="utf-8")
    monkeypatch.setattr(astro, "_NATAL_PATH", path)
    with patch.object(astro, "load_natal_from_notion", return_value=None):
        natal = astro.load_or_compute_natal()
    assert natal == fake_json
