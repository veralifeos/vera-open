"""Testes do dominio Check Semanal."""

import asyncio

from vera.backends.base import StorageBackend
from vera.domains.check_semanal import CheckSemanalDomain


# ---- Fixtures ----


class MockBackend(StorageBackend):
    def __init__(self, data=None):
        self._data = data or []

    async def query(self, collection_id, filters=None, sorts=None, max_pages=1):
        return self._data

    async def query_parallel(self, queries):
        return {q["label"]: self._data for q in queries}

    async def create_record(self, collection_id, properties):
        return {"id": "new"}

    async def update_record(self, record_id, properties):
        return {"id": record_id}

    def extract_text(self, record):
        return ""


def _check_record(semana="S11 (10-16 mar)", energia=7, vida_pratica=6, carreira=8, sanidade=5, highlight="Fechei projeto X"):
    return {
        "id": f"check-{semana}",
        "properties": {
            "Semana": {"type": "title", "title": [{"plain_text": semana}]},
            "Energia": {"type": "number", "number": energia},
            "Vida Pratica": {"type": "number", "number": vida_pratica},
            "Carreira": {"type": "number", "number": carreira},
            "Sanidade": {"type": "number", "number": sanidade},
            "Highlight": {"type": "rich_text", "rich_text": [{"plain_text": highlight}]},
        },
    }


def _domain(records, config_overrides=None):
    config = {"collection": "db-check", "fields": {}}
    if config_overrides:
        config.update(config_overrides)
    backend = MockBackend(records)
    return CheckSemanalDomain(config, backend)


# ---- Collect ----


def test_collect_vazio():
    """Sem collection retorna vazio."""
    domain = CheckSemanalDomain({"collection": "", "fields": {}}, MockBackend([]))
    data = asyncio.run(domain.collect())
    assert data == {"checks": []}


def test_collect_um_registro():
    """Coleta um registro corretamente."""
    domain = _domain([_check_record()])
    data = asyncio.run(domain.collect())
    assert len(data["checks"]) == 1
    check = data["checks"][0]
    assert check["semana"] == "S11 (10-16 mar)"
    assert check["dimensoes"]["Energia"] == 7
    assert check["dimensoes"]["Vida Pratica"] == 6
    assert check["dimensoes"]["Carreira"] == 8
    assert check["dimensoes"]["Sanidade"] == 5
    assert check["highlight"] == "Fechei projeto X"


def test_collect_dois_registros():
    """Coleta no maximo 2 registros (atual + anterior)."""
    records = [
        _check_record("S11 (10-16 mar)", 7, 6, 8, 5, "Semana 11"),
        _check_record("S10 (03-09 mar)", 4, 5, 6, 3, "Semana 10"),
        _check_record("S09 (24-02 mar)", 8, 7, 9, 8, "Semana 09"),
    ]
    domain = _domain(records)
    data = asyncio.run(domain.collect())
    assert len(data["checks"]) == 2


def test_collect_number_none():
    """Dimensao sem valor (None) nao aparece."""
    record = _check_record()
    record["properties"]["Energia"]["number"] = None
    domain = _domain([record])
    data = asyncio.run(domain.collect())
    assert "Energia" not in data["checks"][0]["dimensoes"]


# ---- Analyze ----


def test_analyze_sem_dados():
    """Sem checks retorna indisponivel."""
    domain = _domain([])
    analysis = domain.analyze({"checks": []})
    assert analysis["disponivel"] is False


def test_analyze_faixas_verde():
    """Valores 7-10 sao verde."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 8, "Carreira": 9}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["disponivel"] is True
    assert analysis["faixas"]["Energia"]["faixa"] == "verde"
    assert analysis["faixas"]["Carreira"]["faixa"] == "verde"


def test_analyze_faixas_amarelo():
    """Valores 4-6 sao amarelo."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 5}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["faixas"]["Energia"]["faixa"] == "amarelo"


def test_analyze_faixas_vermelho():
    """Valores 0-3 sao vermelho."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 2}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["faixas"]["Energia"]["faixa"] == "vermelho"
    assert "atencao" in analysis["faixas"]["Energia"]["label"]


def test_analyze_media():
    """Media calculada corretamente."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 8, "Carreira": 6}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["media"] == 7.0


def test_analyze_media_baixa_carga_reduzida():
    """Media < 5 ativa carga reduzida."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 3, "Carreira": 4, "Sanidade": 2, "Vida Pratica": 3}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["carga_reduzida"] is True
    assert analysis["media"] == 3.0


def test_analyze_media_alta_sem_carga_reduzida():
    """Media >= 5 nao ativa carga reduzida."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 7, "Carreira": 8}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["carga_reduzida"] is False


def test_analyze_tendencia_subindo():
    """Tendencia detecta melhora."""
    domain = _domain([])
    data = {"checks": [
        {"semana": "S11", "dimensoes": {"Energia": 7}, "highlight": ""},
        {"semana": "S10", "dimensoes": {"Energia": 4}, "highlight": ""},
    ]}
    analysis = domain.analyze(data)
    assert "subindo" in analysis["tendencia"]["Energia"]


def test_analyze_tendencia_descendo():
    """Tendencia detecta piora."""
    domain = _domain([])
    data = {"checks": [
        {"semana": "S11", "dimensoes": {"Energia": 3}, "highlight": ""},
        {"semana": "S10", "dimensoes": {"Energia": 7}, "highlight": ""},
    ]}
    analysis = domain.analyze(data)
    assert "descendo" in analysis["tendencia"]["Energia"]


def test_analyze_tendencia_estavel():
    """Tendencia estavel quando igual."""
    domain = _domain([])
    data = {"checks": [
        {"semana": "S11", "dimensoes": {"Energia": 5}, "highlight": ""},
        {"semana": "S10", "dimensoes": {"Energia": 5}, "highlight": ""},
    ]}
    analysis = domain.analyze(data)
    assert analysis["tendencia"]["Energia"] == "estavel"


def test_analyze_sem_tendencia_sem_anterior():
    """Sem semana anterior, sem tendencia."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 5}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["tendencia"] == {}


def test_analyze_alerta_forcando():
    """Energia baixa + Carreira alta gera alerta."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 2, "Carreira": 8, "Sanidade": 6, "Vida Pratica": 5}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert any("forcando" in a for a in analysis["alertas"])


def test_analyze_alerta_recuperacao():
    """Energia + Sanidade baixas gera alerta de recuperacao."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 2, "Sanidade": 3, "Carreira": 5, "Vida Pratica": 5}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert any("recuperacao" in a.lower() for a in analysis["alertas"])


def test_analyze_sem_alerta_quando_ok():
    """Sem alertas quando tudo >= 4."""
    domain = _domain([])
    data = {"checks": [{"semana": "S11", "dimensoes": {"Energia": 7, "Carreira": 6, "Sanidade": 8, "Vida Pratica": 5}, "highlight": ""}]}
    analysis = domain.analyze(data)
    assert analysis["alertas"] == []


# ---- Context ----


def test_context_indisponivel():
    """Sem dados retorna string vazia."""
    domain = _domain([])
    ctx = domain.context({}, {"disponivel": False})
    assert ctx == ""


def test_context_com_dados():
    """Contexto contem dimensoes e media."""
    domain = _domain([])
    analysis = {
        "disponivel": True,
        "semana": "S11",
        "faixas": {
            "Energia": {"valor": 7, "faixa": "verde", "label": "semana boa"},
        },
        "media": 7.0,
        "tendencia": {},
        "alertas": [],
        "highlight": "Teste",
        "carga_reduzida": False,
    }
    ctx = domain.context({}, analysis)
    assert "CHECK SEMANAL" in ctx
    assert "Energia: 7/10" in ctx
    assert "Media: 7.0/10" in ctx
    assert "Highlight: Teste" in ctx


def test_context_com_tendencia():
    """Contexto mostra tendencia quando disponivel."""
    domain = _domain([])
    analysis = {
        "disponivel": True,
        "semana": "S11",
        "faixas": {"Energia": {"valor": 7, "faixa": "verde", "label": "semana boa"}},
        "media": 7.0,
        "tendencia": {"Energia": "+3 (subindo)"},
        "alertas": [],
        "highlight": "",
        "carga_reduzida": False,
    }
    ctx = domain.context({}, analysis)
    assert "subindo" in ctx


def test_context_com_alerta():
    """Contexto mostra alertas."""
    domain = _domain([])
    analysis = {
        "disponivel": True,
        "semana": "S11",
        "faixas": {"Energia": {"valor": 2, "faixa": "vermelho", "label": "precisa de atencao"}},
        "media": 2.0,
        "tendencia": {},
        "alertas": ["voce esta forcando"],
        "highlight": "",
        "carga_reduzida": True,
    }
    ctx = domain.context({}, analysis)
    assert "ALERTA" in ctx
    assert "CARGA REDUZIDA" in ctx


# ---- Registry ----


def test_registry_check_semanal():
    """CheckSemanalDomain registrado no DOMAIN_REGISTRY."""
    from vera.domains import DOMAIN_REGISTRY
    assert "check_semanal" in DOMAIN_REGISTRY
