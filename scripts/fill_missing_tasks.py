"""Preenche Esforço + Projeto em tarefas ativas do Notion.

Regras definidas por Fernando em 2026-04-22.

Uso:
  uv run python scripts/fill_missing_tasks.py           # dry-run (default)
  uv run python scripts/fill_missing_tasks.py --apply   # grava no Notion
  uv run python scripts/fill_missing_tasks.py --db-id <uuid>  # override auto-discovery

Lê NOTION_TOKEN do .env. Auto-descobre o DB "Ações Táticas" pelo titulo,
ou aceita --db-id explicito, ou NOTION_DB_ACOES env var.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env", encoding="utf-8-sig")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
if not NOTION_TOKEN:
    print("NOTION_TOKEN nao encontrado no .env", file=sys.stderr)
    sys.exit(2)

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

BASE = "https://api.notion.com/v1"


# --- Regras do Fernando -------------------------------------------------


PROJETO_NAME_PATTERNS = [
    (("[e1-", "[e2-"), "PMMV"),
    (("circo do sufoco",), "Circo do Sufoco"),
    (("linkedin", "post"), "Carreira"),
    (("detector furada", "inpi"), "Pessoal"),
    (("melquías", "melquias", "substack"), "Melquías"),
]

# Se a relation com esse nome tiver itens, mapeia pro projeto
PROJETO_RELATION_MAP = {
    "Proj. PMMV": "PMMV",
    "Proj. Urbba": "Urbba",
    "Proj. Trem Bão": "Trem Bão",
    "Proj. Vera": "Vera",
    "Proj. Letícia": "Letícia",
}

# Area fallback
AREA_TO_PROJETO = {
    "Carreira": "Carreira",
    "Mental": "Pessoal",
}

ESFORCO_RAPIDO = (
    "emitir nf", "validar gsc", "inspecionar robots", "inspecionar sitemap",
    "comunicar", "checkpoint", "ativar toggle",
)
ESFORCO_MEDIO = (
    "auditar", "exportar", "inventariar", "criar redirects", "criar página",
    "criar pagina", "otimizar titles", "implementar schema",
)
ESFORCO_PESADO = (
    "pesquisar demanda", "crawl completo", "diagramar", "produzir relatório",
    "produzir relatorio", "implementar eventos", "qa final", "escrever artigo",
    "dev mvp",
)


def infer_projeto(titulo: str, area: str, relation_names_filled: set[str]) -> str | None:
    # 1. Relations preenchidas
    for rel_name, proj in PROJETO_RELATION_MAP.items():
        if rel_name in relation_names_filled:
            return proj

    lower = titulo.lower()

    # 2. Patterns de nome
    for patterns, proj in PROJETO_NAME_PATTERNS:
        if any(p in lower for p in patterns):
            return proj

    # 3. Area como fallback
    if area in AREA_TO_PROJETO:
        return AREA_TO_PROJETO[area]

    return None


def infer_esforco(titulo: str) -> str | None:
    lower = titulo.lower()
    for kw in ESFORCO_PESADO:
        if kw in lower:
            return "🏋️ Pesado"
    for kw in ESFORCO_MEDIO:
        if kw in lower:
            return "🔧 Médio"
    for kw in ESFORCO_RAPIDO:
        if kw in lower:
            return "⚡ Rápido"
    return None


# --- Notion helpers -----------------------------------------------------


def find_database(name_contains: str = "Ações Táticas") -> str | None:
    """Busca DB pelo titulo via search API."""
    r = requests.post(
        f"{BASE}/search",
        headers=HEADERS,
        json={"filter": {"value": "database", "property": "object"}, "page_size": 100},
        timeout=15,
    )
    r.raise_for_status()
    for db in r.json().get("results", []):
        title = "".join(t.get("plain_text", "") for t in db.get("title", []))
        if name_contains.lower() in title.lower():
            return db["id"]
    return None


def fetch_schema(db_id: str) -> dict:
    r = requests.get(f"{BASE}/databases/{db_id}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json().get("properties", {})


def query_active(db_id: str) -> list[dict]:
    """Query tarefas com Status in [To Do, Doing]."""
    filter_obj = {
        "or": [
            {"property": "Status", "select": {"equals": "To Do"}},
            {"property": "Status", "select": {"equals": "Doing"}},
        ]
    }
    all_results: list[dict] = []
    cursor = None
    while True:
        payload = {"filter": filter_obj, "page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        r = requests.post(
            f"{BASE}/databases/{db_id}/query",
            headers=HEADERS,
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        all_results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return all_results


def patch_page(page_id: str, props: dict) -> bool:
    r = requests.patch(
        f"{BASE}/pages/{page_id}",
        headers=HEADERS,
        json={"properties": props},
        timeout=15,
    )
    if r.status_code >= 400:
        print(f"  [erro] PATCH {page_id[:8]}: {r.status_code} {r.text[:200]}")
        return False
    return True


# --- Main ---------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplicar mudanças (default: dry-run)")
    parser.add_argument("--db-id", default=None, help="Database ID (override)")
    args = parser.parse_args()

    # Resolver DB id
    db_id = args.db_id or os.environ.get("NOTION_DB_ACOES") or find_database("Ações Táticas")
    if not db_id:
        print("Não achei DB 'Ações Táticas'. Passa --db-id", file=sys.stderr)
        return 2
    print(f"DB: {db_id}")

    # Schema pra saber os tipos dos campos
    schema = fetch_schema(db_id)
    esforco_schema = schema.get("Esforço", {})
    projeto_schema = schema.get("Projeto", {})
    esforco_type = esforco_schema.get("type")
    projeto_type = projeto_schema.get("type")
    print(f"Esforço type: {esforco_type}")
    print(f"Projeto type: {projeto_type}")

    if projeto_type == "formula":
        print("ATENCAO: 'Projeto' e formula (readOnly). Vou atualizar apenas 'Esforço'.")
    if esforco_type not in ("select", "rich_text", None):
        print(f"Esforço type inesperado: {esforco_type} — vou tentar select")

    # Query
    pages = query_active(db_id)
    print(f"\n{len(pages)} tarefas ativas (To Do + Doing)")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Modo: {mode}")
    print("=" * 70)

    updates = 0
    esforco_count = 0
    projeto_count = 0
    fails = 0

    for page in pages:
        props = page.get("properties", {})
        title = "".join(
            t.get("plain_text", "") for t in props.get("Name", {}).get("title", [])
        )

        # Esforço atual
        e_prop = props.get("Esforço", {})
        has_esforco = False
        if e_prop.get("type") == "select":
            has_esforco = bool((e_prop.get("select") or {}).get("name"))
        elif e_prop.get("type") == "rich_text":
            has_esforco = bool(e_prop.get("rich_text"))

        # Projeto atual (so check se e select/multi_select — formula nao escreve)
        p_prop = props.get("Projeto", {})
        has_projeto = False
        if p_prop.get("type") == "select":
            has_projeto = bool((p_prop.get("select") or {}).get("name"))
        elif p_prop.get("type") == "multi_select":
            has_projeto = bool(p_prop.get("multi_select"))
        elif p_prop.get("type") == "formula":
            has_projeto = True  # skip — readonly

        # Area
        area = ""
        if props.get("Área", {}).get("type") == "select":
            area = (props["Área"].get("select") or {}).get("name", "")

        # Relations preenchidas
        relation_names_filled = set()
        for name in PROJETO_RELATION_MAP.keys():
            rel_prop = props.get(name, {})
            if rel_prop.get("type") == "relation" and rel_prop.get("relation"):
                relation_names_filled.add(name)

        # Inferir
        novo_esforco = None
        if not has_esforco:
            novo_esforco = infer_esforco(title)

        novo_projeto = None
        if not has_projeto and projeto_type in ("select", "multi_select"):
            novo_projeto = infer_projeto(title, area, relation_names_filled)

        if not novo_esforco and not novo_projeto:
            continue

        # Montar payload
        patch_props: dict = {}
        log_parts = []
        if novo_esforco and esforco_type == "select":
            patch_props["Esforço"] = {"select": {"name": novo_esforco}}
            log_parts.append(f"Esforço={novo_esforco}")
        elif novo_esforco and esforco_type == "rich_text":
            patch_props["Esforço"] = {
                "rich_text": [{"text": {"content": novo_esforco}}]
            }
            log_parts.append(f"Esforço={novo_esforco} (rich_text)")

        if novo_projeto and projeto_type == "select":
            patch_props["Projeto"] = {"select": {"name": novo_projeto}}
            log_parts.append(f"Projeto={novo_projeto}")
        elif novo_projeto and projeto_type == "multi_select":
            patch_props["Projeto"] = {"multi_select": [{"name": novo_projeto}]}
            log_parts.append(f"Projeto={novo_projeto}")

        if not patch_props:
            continue

        print(f"  [{title[:60]}] {' | '.join(log_parts)}")

        if args.apply:
            ok = patch_page(page["id"], patch_props)
            if ok:
                updates += 1
                if "Esforço" in patch_props:
                    esforco_count += 1
                if "Projeto" in patch_props:
                    projeto_count += 1
            else:
                fails += 1
        else:
            updates += 1
            if "Esforço" in patch_props:
                esforco_count += 1
            if "Projeto" in patch_props:
                projeto_count += 1

    print("=" * 70)
    print(
        f"{mode}: {updates} tarefa(s) "
        f"({esforco_count} Esforço, {projeto_count} Projeto, {fails} falhas)"
    )
    if not args.apply:
        print("\nPara aplicar de verdade: rodar com --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
