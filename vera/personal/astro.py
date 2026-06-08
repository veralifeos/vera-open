"""Calculos astrologicos — transitos diarios, aspectos e leitura via Claude.

Portado de vera-private/vera/astro.py. Usa pyswisseph para posicoes
planetarias reais. Mapa natal lido nesta ordem:
  1. Notion page (se NOTION_PAGE_NATAL setada e parseavel)
  2. config/natal_chart.json (cache local)
  3. calcular_natal() in-place com dados hardcoded de nascimento

Linha do Ceu continua como antes: lida do Notion DB (NOTION_DB_LINHA_CEU).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from vera.personal.config import (
    ANTHROPIC_API_KEY,
    BRT,
    NOTION_DB_ACOES,
    NOTION_DB_LINHA_CEU,
    NOTION_PAGE_NATAL,
)
from vera.personal.notion_client import (
    extrair_texto,
    fetch_notion_page_blocks,
    query_notion_database,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _REPO_ROOT / "config"
_NATAL_PATH = _CONFIG_DIR / "natal_chart.json"

# Dados fixos de nascimento (fallback para calcular o mapa)
_NASCIMENTO = {
    "year": 1989, "month": 1, "day": 3,
    "hour": 0, "minute": 13,
    "lat": -20.5331, "lon": -44.7089,
    "tz_offset": -3,
}

SIGNOS = [
    "Aries", "Touro", "Gemeos", "Cancer", "Leao", "Virgem",
    "Libra", "Escorpiao", "Sagitario", "Capricornio", "Aquario", "Peixes",
]

PLANETAS = {
    0: "Sol", 1: "Lua", 2: "Mercurio", 3: "Venus", 4: "Marte",
    5: "Jupiter", 6: "Saturno", 7: "Urano", 8: "Netuno", 9: "Plutao",
}

ASPECTOS = {
    "conjuncao": 0, "sextil": 60, "quadratura": 90,
    "trigono": 120, "oposicao": 180,
}


def _lon_to_sign(lon: float) -> tuple[str, float]:
    idx = int(lon / 30)
    grau = round(lon % 30, 1)
    return SIGNOS[idx % 12], grau


def _julian_day(year: int, month: int, day: int, hour: float = 12.0) -> float:
    import swisseph as swe
    return swe.julday(year, month, day, hour)


def calcular_posicoes(year: int, month: int, day: int, hour: float = 12.0) -> dict:
    """Posicoes planetarias para uma data/hora."""
    import swisseph as swe
    swe.set_ephe_path("")

    jd = _julian_day(year, month, day, hour)
    posicoes: dict[str, dict] = {}
    for planet_id, nome in PLANETAS.items():
        result, _ = swe.calc_ut(jd, planet_id)
        lon = result[0]
        signo, grau = _lon_to_sign(lon)
        posicoes[nome] = {"longitude": round(lon, 2), "signo": signo, "grau": grau}
    return posicoes


def calcular_natal() -> dict:
    """Mapa natal do Fernando (hardcoded do arquivo privado)."""
    import swisseph as swe
    swe.set_ephe_path("")

    n = _NASCIMENTO
    hour_utc = n["hour"] + n["minute"] / 60.0 - n["tz_offset"]
    jd = _julian_day(n["year"], n["month"], n["day"], hour_utc)

    natal: dict[str, dict] = {}
    for planet_id, nome in PLANETAS.items():
        result, _ = swe.calc_ut(jd, planet_id)
        lon = result[0]
        signo, grau = _lon_to_sign(lon)
        natal[nome] = {"longitude": round(lon, 2), "signo": signo, "grau": grau}

    houses, ascmc = swe.houses(jd, n["lat"], n["lon"], b"P")
    asc_lon = ascmc[0]
    mc_lon = ascmc[1]
    signo_asc, grau_asc = _lon_to_sign(asc_lon)
    signo_mc, grau_mc = _lon_to_sign(mc_lon)
    natal["ASC"] = {"longitude": round(asc_lon, 2), "signo": signo_asc, "grau": grau_asc}
    natal["MC"] = {"longitude": round(mc_lon, 2), "signo": signo_mc, "grau": grau_mc}

    return natal


# --- Notion natal chart loader -----------------------------------------

# Regex tenta capturar "Planeta: Signo grau" ou "Planeta em Signo grau"
# Exemplos aceitos: "Sol: Capricornio 13", "Lua em Escorpiao 15.2"
_NATAL_LINE_RE = re.compile(
    r"(?P<planeta>Sol|Lua|Mercurio|Venus|Marte|Jupiter|Saturno|Urano|Netuno|Plut[aã]o|ASC|Ascendente|MC|Meio do C[eé]u)"
    r"\s*[:em]{1,2}\s*"
    r"(?P<signo>[A-Za-zÁÉÍÓÚÂÊÎÔÛÃÕÇáéíóúâêîôûãõç]+)"
    r"\s*(?P<grau>\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

_SIGNO_ALIASES = {
    "aries": "Aries", "áries": "Aries",
    "touro": "Touro",
    "gemeos": "Gemeos", "gêmeos": "Gemeos",
    "cancer": "Cancer", "câncer": "Cancer",
    "leao": "Leao", "leão": "Leao",
    "virgem": "Virgem",
    "libra": "Libra",
    "escorpiao": "Escorpiao", "escorpião": "Escorpiao",
    "sagitario": "Sagitario", "sagitário": "Sagitario",
    "capricornio": "Capricornio", "capricórnio": "Capricornio",
    "aquario": "Aquario", "aquário": "Aquario",
    "peixes": "Peixes",
}

_PLANETA_ALIASES = {
    "sol": "Sol",
    "lua": "Lua",
    "mercurio": "Mercurio",
    "mercúrio": "Mercurio",
    "venus": "Venus",
    "vênus": "Venus",
    "marte": "Marte",
    "jupiter": "Jupiter",
    "júpiter": "Jupiter",
    "saturno": "Saturno",
    "urano": "Urano",
    "netuno": "Netuno",
    "plutao": "Plutao",
    "plutão": "Plutao",
    "asc": "ASC",
    "ascendente": "ASC",
    "mc": "MC",
    "meio do ceu": "MC",
    "meio do céu": "MC",
}


def _normalize_planeta(raw: str) -> str:
    return _PLANETA_ALIASES.get(raw.strip().lower(), "")


def _block_text(block: dict) -> str:
    """Extrai texto de um block Notion (paragraph, heading_N, bulleted_list_item)."""
    btype = block.get("type", "")
    inner = block.get(btype, {})
    return extrair_texto(inner.get("rich_text", []))


def load_natal_from_notion(page_id: str | None = None) -> dict | None:
    """Tenta montar o mapa natal a partir de uma pagina Notion.

    O parser e deliberadamente tolerante: varre blocks procurando linhas
    no formato "Planeta: Signo grau". Retorna None se nao achar 3+ planetas
    (sinal de que a pagina nao tem o formato esperado).
    """
    pid = page_id or NOTION_PAGE_NATAL
    if not pid:
        return None

    try:
        blocks = fetch_notion_page_blocks(pid)
    except Exception as e:
        logger.warning("Falha ao buscar mapa natal do Notion: %s", e)
        return None

    natal: dict[str, dict] = {}
    for block in blocks:
        text = _block_text(block)
        if not text:
            continue
        for match in _NATAL_LINE_RE.finditer(text):
            planeta = _normalize_planeta(match.group("planeta"))
            if not planeta:
                continue
            signo_raw = match.group("signo").lower()
            signo = _SIGNO_ALIASES.get(signo_raw)
            if not signo:
                continue
            grau_str = match.group("grau").replace(",", ".")
            try:
                grau = float(grau_str)
            except ValueError:
                continue
            # Longitude derivada: index do signo * 30 + grau
            idx = SIGNOS.index(signo)
            lon = idx * 30 + grau
            natal[planeta] = {
                "longitude": round(lon, 2),
                "signo": signo,
                "grau": round(grau, 1),
            }

    if len(natal) < 3:
        logger.info(
            "Mapa natal do Notion incompleto (%d entradas) — usando fallback json",
            len(natal),
        )
        return None

    return natal


def load_or_compute_natal() -> dict:
    """Ordem: Notion -> cache json -> calcular in-place."""
    # 1. Notion
    from_notion = load_natal_from_notion()
    if from_notion:
        return from_notion

    # 2. Cache json
    if _NATAL_PATH.exists():
        try:
            return json.loads(_NATAL_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Calcular e salvar cache
    natal = calcular_natal()
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _NATAL_PATH.write_text(json.dumps(natal, ensure_ascii=False, indent=2), encoding="utf-8")
    return natal


# --- Aspectos -----------------------------------------------------------


def calcular_aspectos(transitos: dict, natal: dict) -> list[dict]:
    """Aspectos entre transitos e natal (orbes 4-6)."""
    aspectos_encontrados: list[dict] = []
    for t_nome, t_data in transitos.items():
        t_lon = t_data["longitude"]
        orbe_max = 6.0 if t_nome in ("Sol", "Lua") else 4.0

        for n_nome, n_data in natal.items():
            if n_nome in ("ASC", "MC") and t_nome not in ("Sol", "Lua", "Mercurio", "Venus", "Marte"):
                continue
            n_lon = n_data["longitude"]
            for asp_nome, asp_angulo in ASPECTOS.items():
                diff = abs(t_lon - n_lon)
                if diff > 180:
                    diff = 360 - diff
                orbe = abs(diff - asp_angulo)
                if orbe <= orbe_max:
                    aspectos_encontrados.append({
                        "transito": f"{t_nome} em {t_data['signo']} {t_data['grau']}",
                        "natal": f"{n_nome} natal em {n_data['signo']} {n_data['grau']}",
                        "aspecto": asp_nome,
                        "orbe": round(orbe, 1),
                    })

    prioridade = {"Sol": 0, "Lua": 1, "ASC": 2, "MC": 3}
    aspectos_encontrados.sort(
        key=lambda a: (prioridade.get(a["natal"].split(" ")[0], 9), a["orbe"])
    )
    return aspectos_encontrados


# --- Contexto Notion (marcos + tarefas) --------------------------------


def _buscar_marcos_ativos() -> list[dict]:
    """Marcos da Linha do Ceu ativos hoje."""
    if not NOTION_DB_LINHA_CEU:
        return []
    try:
        hoje = datetime.now(BRT).date().isoformat()
        filter_obj = {
            "and": [
                {"property": "Janela", "date": {"on_or_before": hoje}},
                {
                    "or": [
                        {"property": "Janela", "date": {"on_or_after": hoje}},
                    ]
                },
            ]
        }
        data = query_notion_database(NOTION_DB_LINHA_CEU, filter_obj)
        marcos: list[dict] = []
        for page in data.get("results", []):
            props = page["properties"]
            nome = extrair_texto(props.get("Name", {}).get("title", []))
            regra = extrair_texto(props.get("Regra prática", {}).get("rich_text", []))
            marcos.append({"nome": nome, "regra": regra})
        return marcos
    except Exception as e:
        logger.warning("Erro ao buscar marcos: %s", e)
        return []


def _buscar_tarefas_proximas() -> list[str]:
    """Tarefas com deadline nos proximos 3 dias."""
    if not NOTION_DB_ACOES:
        return []
    try:
        hoje = datetime.now(BRT).date()
        tres_dias = (hoje + timedelta(days=3)).isoformat()
        filter_obj = {
            "and": [
                {"property": "Status", "select": {"does_not_equal": "Done"}},
                {"property": "Status", "select": {"does_not_equal": "Skip"}},
                {"property": "Deadline", "date": {"on_or_before": tres_dias}},
            ]
        }
        data = query_notion_database(NOTION_DB_ACOES, filter_obj)
        tarefas: list[str] = []
        for page in data.get("results", []):
            props = page["properties"]
            nome = extrair_texto(props.get("Name", {}).get("title", []))
            deadline_prop = props.get("Deadline", {}).get("date")
            deadline = deadline_prop.get("start") if deadline_prop else ""
            tarefas.append(f"{nome} (deadline: {deadline})")
        return tarefas
    except Exception as e:
        logger.warning("Erro ao buscar tarefas: %s", e)
        return []


# --- Interpretacao ------------------------------------------------------


def _gerar_interpretacao(transitos: dict, aspectos: list, marcos: list, tarefas: list) -> str:
    """Interpretacao via Claude Haiku. Fallback texto simples se sem API key."""
    if not ANTHROPIC_API_KEY:
        return _formato_texto_simples(transitos, aspectos, marcos, tarefas)

    from anthropic import Anthropic

    hoje = datetime.now(BRT)
    transitos_txt = "\n".join(
        f"- {nome}: {d['signo']} {d['grau']}" for nome, d in transitos.items()
    )
    aspectos_txt = "\n".join(
        f"- {a['transito']} {a['aspecto']} {a['natal']} (orbe {a['orbe']})"
        for a in aspectos[:10]
    ) or "Nenhum aspecto significativo."
    marcos_txt = "\n".join(
        f"- {m['nome']}: {m['regra']}" for m in marcos
    ) or "Sem marco ativo."
    tarefas_txt = "\n".join(f"- {t}" for t in tarefas[:5]) or "Sem tarefas urgentes."

    prompt = f"""Voce eh a Vera, assistente pessoal de Fernando Fidelis.

MAPA NATAL:
- Sol: Capricornio (13 graus)
- Lua: Escorpiao
- Ascendente: Libra
- Orixas: Cabeca de Oxalufa, odus de Yemanja

TRANSITOS DO DIA ({hoje.strftime('%d/%m/%Y')}):
{transitos_txt}

ASPECTOS AO NATAL:
{aspectos_txt}

LINHA DO CEU (marcos ativos):
{marcos_txt}

TAREFAS PROXIMAS:
{tarefas_txt}

INSTRUCOES:
- Gere uma leitura astrologica pratica do dia em 150-200 palavras
- Conecte transitos com tarefas concretas do Fernando
- Tom: direto, pratico, sem misticismo excessivo. A Vera fala como secretaria experiente que entende de astrologia
- Mencione aspectos mais relevantes (ao Sol, Lua, ASC)
- Se houver marco da Linha do Ceu, integre na leitura
- Termine com 1 sugestao concreta pro dia
- PT-BR, sem emojis"""

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _formato_texto_simples(transitos: dict, aspectos: list, marcos: list, tarefas: list) -> str:
    hoje = datetime.now(BRT)
    lines = [f"Ceu de {hoje.strftime('%d/%m/%Y')}:", ""]
    lines.append("Transitos:")
    for nome, d in transitos.items():
        lines.append(f"  {nome}: {d['signo']} {d['grau']}")
    if aspectos:
        lines.append("\nAspectos ao natal:")
        for a in aspectos[:5]:
            lines.append(f"  {a['transito']} {a['aspecto']} {a['natal']} (orbe {a['orbe']})")
    if marcos:
        lines.append("\nLinha do Ceu:")
        for m in marcos:
            lines.append(f"  {m['nome']}: {m['regra']}")
    if tarefas:
        lines.append("\nTarefas proximas:")
        for t in tarefas[:3]:
            lines.append(f"  {t}")
    return "\n".join(lines)


def gerar_leitura_ceu() -> str:
    """Leitura astrologica completa do dia."""
    agora = datetime.now(BRT)
    transitos = calcular_posicoes(agora.year, agora.month, agora.day, 15.0)
    natal = load_or_compute_natal()
    aspectos = calcular_aspectos(transitos, natal)
    marcos = _buscar_marcos_ativos()
    tarefas = _buscar_tarefas_proximas()
    return _gerar_interpretacao(transitos, aspectos, marcos, tarefas)
