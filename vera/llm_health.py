"""Circuit breaker para o LLM provider.

Rastreia falhas consecutivas em state/llm_health.json. Depois do threshold,
o briefing para de tentar chamar o Claude e devolve uma mensagem curta
humana em vez de stacktrace no Telegram. Quando o Claude voltar, um run
bem sucedido reseta o contador.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = _REPO_ROOT / "state" / "llm_health.json"

_DEFAULT_STATE = {
    "consecutive_failures": 0,
    "last_failure": None,
    "last_failure_error": None,
    "last_success": None,
}


def _load(path: Path | None = None) -> dict:
    p = path or DEFAULT_PATH
    try:
        return {**_DEFAULT_STATE, **json.loads(p.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULT_STATE)


def _save(state: dict, path: Path | None = None) -> None:
    p = path or DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def record_success(path: Path | None = None) -> None:
    """LLM respondeu — zera contador, atualiza last_success."""
    state = _load(path)
    state["consecutive_failures"] = 0
    state["last_success"] = datetime.now(timezone.utc).isoformat()
    state["last_failure_error"] = None
    _save(state, path)


def record_failure(error: str, path: Path | None = None) -> int:
    """Incrementa contador de falhas. Retorna o novo count."""
    state = _load(path)
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
    state["last_failure"] = datetime.now(timezone.utc).isoformat()
    state["last_failure_error"] = (error or "")[:200]
    _save(state, path)
    return state["consecutive_failures"]


def is_circuit_open(threshold: int = 3, path: Path | None = None) -> bool:
    """Retorna True se contagem de falhas consecutivas >= threshold."""
    state = _load(path)
    return state.get("consecutive_failures", 0) >= threshold


def get_status(path: Path | None = None) -> dict:
    """Snapshot do health state, para debug/doctor."""
    return _load(path)


def humanized_offline_message(error: str | None = None) -> str:
    """Texto curto e humano pra mandar quando o LLM esta off.

    Sem stacktrace, sem detalhes tecnicos — so avisa que Vera ta em silencio
    ate resolver. Opcionalmente inclui uma dica curta se o erro for conhecido.
    """
    err = (error or "").lower()
    if "credit balance" in err or "credit" in err:
        dica = "Olha o saldo da Anthropic."
    elif "rate" in err and "limit" in err:
        dica = "Rate limit — deve voltar em alguns minutos."
    elif "auth" in err or "401" in err or "invalid api key" in err:
        dica = "API key pode ter expirado ou sido revogada."
    elif "timeout" in err or "connection" in err:
        dica = "Problema de rede — tenta de novo daqui a pouco."
    else:
        dica = "Me chama quando resolver."

    return (
        "☕ Vera em silencio hoje.\n\n"
        "LLM fora do ar ha algumas tentativas. "
        f"{dica}\n\n"
        "Volto quando voltar."
    )
