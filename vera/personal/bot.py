"""Bot bidirecional Telegram — processa comandos pendentes via getUpdates.

Portado de vera-private/vera/bot.py. Nao faz polling continuo — busca
mensagens pendentes, processa, responde, limpa. No open e chamado pelo
workflow bot.yml a cada 30 min.

Comandos:
  /status  — pipeline + tarefas urgentes
  /check   — Check Semanal (preenche ou mostra)
  /feito   — marca tarefa como Done
  /ceu     — leitura astrologica do dia (cache diario)
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests

from vera.personal.config import (
    BRT,
    NOTION_DB_ACOES,
    NOTION_DB_CHECK,
    NOTION_DB_PIPELINE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from vera.personal.notion_client import (
    create_notion_page,
    extrair_texto,
    query_notion_database,
    update_notion_page,
)

logger = logging.getLogger(__name__)

_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "state"
_BOT_STATE_PATH = _STATE_DIR / "bot_state.json"
_BOT_PENDING_PATH = _STATE_DIR / "bot_pending.json"


def _telegram_api() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# --- State --------------------------------------------------------------


def load_bot_state() -> dict:
    if _BOT_STATE_PATH.exists():
        try:
            return json.loads(_BOT_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_update_id": 0,
        "silence_until": None,
        "last_ceu": None,
        "last_ceu_text": None,
    }


def save_bot_state(state: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _BOT_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_pending() -> dict:
    if _BOT_PENDING_PATH.exists():
        try:
            return json.loads(_BOT_PENDING_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_pending(data: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _BOT_PENDING_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clear_pending() -> None:
    if _BOT_PENDING_PATH.exists():
        _BOT_PENDING_PATH.unlink()


# --- Telegram API -------------------------------------------------------


def get_updates(offset: int = 0, timeout: int = 5) -> list[dict]:
    try:
        resp = requests.get(
            f"{_telegram_api()}/getUpdates",
            params={"offset": offset, "timeout": timeout},
            timeout=timeout + 5,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception as e:
        logger.warning("Erro ao buscar updates: %s", e)
        return []


def send_reply(text: str, chat_id: str | None = None) -> bool:
    cid = chat_id or TELEGRAM_CHAT_ID
    try:
        resp = requests.post(
            f"{_telegram_api()}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Erro ao enviar (markdown): %s", e)
        try:
            resp = requests.post(
                f"{_telegram_api()}/sendMessage",
                json={"chat_id": cid, "text": text},
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception:
            return False


# --- /status ------------------------------------------------------------


def cmd_status() -> str:
    lines: list[str] = []
    if NOTION_DB_PIPELINE:
        filter_obj = {
            "and": [
                {"property": "Estágio", "select": {"does_not_equal": "Descartei"}},
                {"property": "Estágio", "select": {"does_not_equal": "Ghost"}},
                {"property": "Estágio", "select": {"does_not_equal": "Arquivada"}},
            ]
        }
        data = query_notion_database(NOTION_DB_PIPELINE, filter_obj)
        contagem: dict[str, int] = {}
        for page in data.get("results", []):
            estagio = page.get("properties", {}).get("Estágio", {}).get("select", {})
            nome = estagio.get("name", "Sem estágio") if estagio else "Sem estágio"
            contagem[nome] = contagem.get(nome, 0) + 1
        if contagem:
            lines.append("Pipeline:")
            ordenados = ("Mapeada", "Aplicada", "Entrevista", "Proposta", "Fechou")
            for est in ordenados:
                if est in contagem:
                    lines.append(f"  {est}: {contagem[est]}")
            for est, n in sorted(contagem.items()):
                if est not in ordenados:
                    lines.append(f"  {est}: {n}")
        else:
            lines.append("Pipeline: vazio")

    if NOTION_DB_ACOES:
        hoje = datetime.now(BRT).date()
        sete_dias = (hoje + timedelta(days=7)).isoformat()
        filter_obj = {
            "and": [
                {"property": "Status", "select": {"does_not_equal": "Done"}},
                {"property": "Status", "select": {"does_not_equal": "Skip"}},
                {
                    "or": [
                        {"property": "Deadline", "date": {"on_or_before": sete_dias}},
                        {"property": "Status", "select": {"equals": "Doing"}},
                    ]
                },
            ]
        }
        sorts = [{"property": "Deadline", "direction": "ascending"}]
        data = query_notion_database(NOTION_DB_ACOES, filter_obj, sorts)
        tarefas: list[tuple[str, str, str | None]] = []
        for page in data.get("results", []):
            props = page["properties"]
            nome = extrair_texto(props.get("Name", {}).get("title", []))
            status = props.get("Status", {}).get("select", {}).get("name", "")
            deadline_prop = props.get("Deadline", {}).get("date")
            deadline = deadline_prop.get("start") if deadline_prop else None
            tarefas.append((status, nome, deadline))
        if tarefas:
            lines.append("")
            lines.append(f"Tarefas urgentes ({len(tarefas)}):")
            for status, nome, deadline in tarefas[:10]:
                tag = status.upper() if status else "TODO"
                dl = f" ({_format_date(deadline)})" if deadline else ""
                lines.append(f"  [{tag}] {nome}{dl}")
        else:
            lines.append("\nSem tarefas urgentes.")

    return "\n".join(lines) if lines else "Sem dados disponiveis."


# --- /check -------------------------------------------------------------


def _semana_atual() -> tuple[str, str, str]:
    hoje = datetime.now(BRT).date()
    seg = hoje - timedelta(days=hoje.weekday())
    dom = seg + timedelta(days=6)
    n = hoje.isocalendar()[1]
    meses = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]
    mes = meses[seg.month - 1]
    label = f"S{n} ({seg.day}-{dom.day} {mes})"
    return label, seg.isoformat(), dom.isoformat()


def cmd_check(args: list[str]) -> str:
    if not NOTION_DB_CHECK:
        return "NOTION_DB_CHECK nao configurado."

    if args:
        if len(args) != 4:
            return "Formato: /check [energia] [vida] [carreira] [sanidade]\nExemplo: /check 7 6 8 5"
        try:
            valores = [int(a) for a in args]
        except ValueError:
            return "Valores devem ser numeros inteiros (0-10)."
        for v in valores:
            if v < 0 or v > 10:
                return f"Valor {v} fora do range (0-10)."

        energia, vida, carreira, sanidade = valores
        media = round(sum(valores) / 4, 1)
        label, _, _ = _semana_atual()

        sorts = [{"property": "Semana", "direction": "descending"}]
        data = query_notion_database(NOTION_DB_CHECK, sorts=sorts)
        existing_page = None
        for page in data.get("results", []):
            title = extrair_texto(page["properties"].get("Semana", {}).get("title", []))
            if title == label:
                existing_page = page
                break

        props = {
            "Energia": {"number": energia},
            "Vida Pratica": {"number": vida},
            "Carreira": {"number": carreira},
            "Sanidade": {"number": sanidade},
        }
        if existing_page:
            update_notion_page(existing_page["id"], props)
        else:
            props["Semana"] = {"title": [{"text": {"content": label}}]}
            create_notion_page(NOTION_DB_CHECK, props)

        return (
            f"Check {label} salvo:\n"
            f"  Energia: {energia}\n"
            f"  Vida Pratica: {vida}\n"
            f"  Carreira: {carreira}\n"
            f"  Sanidade: {sanidade}\n"
            f"  Media: {media}"
        )

    sorts = [{"property": "Semana", "direction": "descending"}]
    data = query_notion_database(NOTION_DB_CHECK, sorts=sorts)
    results = data.get("results", [])
    if not results:
        return "Nenhum check preenchido.\nPra preencher: /check 7 6 8 5"
    page = results[0]
    props = page["properties"]
    semana = extrair_texto(props.get("Semana", {}).get("title", []))
    e = props.get("Energia", {}).get("number")
    v = props.get("Vida Pratica", {}).get("number")
    c = props.get("Carreira", {}).get("number")
    s = props.get("Sanidade", {}).get("number")
    vals = [x for x in (e, v, c, s) if x is not None]
    media = round(sum(vals) / len(vals), 1) if vals else 0
    return (
        f"Check {semana}:\n"
        f"  Energia: {e} | Vida Pratica: {v}\n"
        f"  Carreira: {c} | Sanidade: {s}\n"
        f"  Media: {media}\n\n"
        f"Pra atualizar: /check {e or 5} {v or 5} {c or 5} {s or 5}"
    )


# --- /feito -------------------------------------------------------------


def cmd_feito(args: list[str]) -> tuple[str, dict | None]:
    if not NOTION_DB_ACOES:
        return "NOTION_DB_ACOES nao configurado.", None
    query = " ".join(args).strip()
    if not query:
        return "Formato: /feito [trecho do nome]\nExemplo: /feito detector furada", None

    filter_obj = {
        "and": [
            {"property": "Name", "rich_text": {"contains": query}},
            {"property": "Status", "select": {"does_not_equal": "Done"}},
            {"property": "Status", "select": {"does_not_equal": "Skip"}},
        ]
    }
    data = query_notion_database(NOTION_DB_ACOES, filter_obj)
    results = data.get("results", [])
    if not results:
        return f'Nao achei tarefa com "{query}".', None

    if len(results) == 1:
        page = results[0]
        nome = extrair_texto(page["properties"].get("Name", {}).get("title", []))
        status_old = page["properties"].get("Status", {}).get("select", {}).get("name", "")
        update_notion_page(page["id"], {"Status": {"select": {"name": "Done"}}})
        return f"Feito: {nome}\n(era {status_old}, agora Done)", None

    lines = [f"Achei {len(results)} tarefas:"]
    options: list[dict] = []
    for i, page in enumerate(results[:5], 1):
        nome = extrair_texto(page["properties"].get("Name", {}).get("title", []))
        status = page["properties"].get("Status", {}).get("select", {}).get("name", "")
        lines.append(f"{i}. {nome} ({status})")
        options.append({"id": page["id"], "nome": nome, "status": status})
    lines.append("\nResponde com o numero.")
    return "\n".join(lines), {"command": "feito", "options": options}


def resolve_pending(choice: int, pending: dict) -> str:
    options = pending.get("options", [])
    if choice < 1 or choice > len(options):
        return f"Numero invalido. Escolha entre 1 e {len(options)}."
    opt = options[choice - 1]
    update_notion_page(opt["id"], {"Status": {"select": {"name": "Done"}}})
    return f"Feito: {opt['nome']}\n(era {opt['status']}, agora Done)"


# --- /ceu --------------------------------------------------------------


def cmd_ceu(state: dict) -> tuple[str, dict]:
    """Leitura astrologica — cache diario para economizar chamadas."""
    hoje = datetime.now(BRT).date().isoformat()
    if state.get("last_ceu") == hoje and state.get("last_ceu_text"):
        return state["last_ceu_text"], state

    try:
        from vera.personal.astro import gerar_leitura_ceu
        texto = gerar_leitura_ceu()
    except ImportError:
        texto = "pyswisseph nao instalado. /ceu indisponivel."
    except Exception as e:
        logger.warning("Erro no /ceu: %s", e)
        texto = f"Erro ao gerar /ceu: {e}"

    state["last_ceu"] = hoje
    state["last_ceu_text"] = texto
    return texto, state


# --- Dispatch -----------------------------------------------------------


HELP_TEXT = (
    "Comandos disponiveis:\n"
    "/status - Pipeline + tarefas urgentes\n"
    "/check [e] [v] [c] [s] - Check Semanal\n"
    "/feito [trecho] - Marcar tarefa Done\n"
    "/ceu - Leitura astrologica do dia"
)


def parse_command(text: str) -> tuple[str | None, list[str]]:
    text = text.strip()
    if not text.startswith("/"):
        return None, []
    parts = text.split()
    cmd = parts[0].lower().split("@")[0]
    return cmd, parts[1:]


def process_message(text: str, state: dict) -> tuple[str, dict, dict | None]:
    cmd, args = parse_command(text)
    if cmd is None:
        pending = load_pending()
        if pending and text.strip().isdigit():
            choice = int(text.strip())
            resp = resolve_pending(choice, pending)
            clear_pending()
            return resp, state, None
        return "", state, None

    if cmd == "/status":
        return cmd_status(), state, None
    if cmd == "/check":
        return cmd_check(args), state, None
    if cmd == "/feito":
        resp, pending = cmd_feito(args)
        return resp, state, pending
    if cmd == "/ceu":
        resp, state = cmd_ceu(state)
        return resp, state, None
    if cmd.startswith("/"):
        return f"Comando nao reconhecido.\n\n{HELP_TEXT}", state, None
    return "", state, None


# --- Main loop ----------------------------------------------------------


def process_pending_updates(dry_run: bool = False) -> int:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Bot: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID nao configurado.")
        return 0

    state = load_bot_state()
    offset = state.get("last_update_id", 0)
    if offset:
        offset += 1

    updates = get_updates(offset=offset, timeout=2)
    if not updates:
        print("Bot: nenhum comando pendente.")
        return 0

    print(f"Bot: {len(updates)} mensagens pendentes.")
    processed = 0

    for update in updates:
        update_id = update.get("update_id", 0)
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "")

        if chat_id != str(TELEGRAM_CHAT_ID):
            logger.warning("Mensagem de chat desconhecido: %s", chat_id)
            state["last_update_id"] = update_id
            continue

        if not text:
            state["last_update_id"] = update_id
            continue

        print(f"  Processando: {text[:50]}")
        try:
            response, state, pending = process_message(text, state)
            if pending:
                save_pending(pending)
            if response and not dry_run:
                send_reply(response, chat_id)
            elif response:
                print(f"  [dry-run] Resposta: {response[:100]}")
        except Exception as e:
            logger.warning("Erro ao processar '%s': %s", text[:30], e)
            if not dry_run:
                send_reply(f"Erro ao processar: {e}", chat_id)

        state["last_update_id"] = update_id
        processed += 1

    save_bot_state(state)
    print(f"Bot: {processed} comandos processados.")
    return processed


# --- Utils --------------------------------------------------------------


def _format_date(iso_date: str | None) -> str:
    if not iso_date:
        return ""
    try:
        d = datetime.fromisoformat(iso_date).date()
        meses = ["jan", "fev", "mar", "abr", "mai", "jun",
                 "jul", "ago", "set", "out", "nov", "dez"]
        return f"{d.day:02d}/{meses[d.month - 1]}"
    except (ValueError, IndexError):
        return iso_date[:10]


# --- CLI entry ----------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Vera Bot — processa comandos Telegram")
    parser.add_argument("--process", action="store_true", help="Processa comandos pendentes")
    parser.add_argument("--dry-run", action="store_true", help="Nao envia respostas")
    args = parser.parse_args()
    if args.process:
        process_pending_updates(dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
