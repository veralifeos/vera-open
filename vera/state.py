"""State management — persistência entre runs via JSON no Git.

Estratégia:
  - Source of truth: state/briefing_state.json (commitado pelo workflow).
  - Fallback local: para dev sem repo.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

STATE_VAZIO = {
    "last_run_date": None,
    "last_payload_hash": None,
    "mention_counts": {},
    "last_snapshot": {},
    "briefing_count": 0,
}

# Threshold para zombie (mention_count >= threshold → cooldown)
ZOMBIE_THRESHOLD = 8
COOLDOWN_DAYS = 7


class StateManager:
    """Gerencia state do briefing."""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or (_REPO_ROOT / "state")
        self.state_path = self.state_dir / "briefing_state.json"
        self._fallback_path = Path(os.environ.get("VERA_STATE_PATH", "/tmp/vera_state.json"))

    def load(self) -> dict:
        """Carrega state: Git file → fallback local → vazio."""
        # 1. Git-based state (source of truth)
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                last_run = state.get("last_run_date", "nunca")
                mc_count = len(state.get("mention_counts", {}))
                print(
                    f"   [state] Carregado de {self.state_path.name} "
                    f"| último run: {last_run} | {mc_count} mention_counts"
                )
                return state
            except (json.JSONDecodeError, Exception) as e:
                print(f"   [state] State corrompido: {e}")

        # 2. Fallback local
        if self._fallback_path.exists():
            try:
                state = json.loads(self._fallback_path.read_text(encoding="utf-8"))
                print(f"   [state] Carregado de fallback local ({self._fallback_path})")
                return state
            except Exception as e:
                print(f"   [state] Fallback local corrompido: {e}")

        print("   [state] Nenhum state encontrado. Iniciando do zero.")
        return dict(STATE_VAZIO)

    def save(self, state: dict, dry_run: bool = False) -> bool:
        """Salva state no JSON. Retorna True se OK."""
        if dry_run:
            print("   [state] Dry run — não salvou.")
            return True

        state_com_meta = {
            **state,
            "_last_saved": datetime.now(timezone.utc).isoformat(),
            "_saved_by": "vera-open-v2",
        }
        conteudo = json.dumps(state_com_meta, indent=2, ensure_ascii=False)

        # Git-based state
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(conteudo, encoding="utf-8")
            mc_count = len(state.get("mention_counts", {}))
            print(f"   [state] Salvo em {self.state_path.name} | {mc_count} mention_counts")
            return True
        except Exception as e:
            print(f"   [state] Falha ao salvar: {e}")

        # Fallback local
        try:
            self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
            self._fallback_path.write_text(conteudo, encoding="utf-8")
            print(f"   [state] Salvo em fallback local ({self._fallback_path})")
            return True
        except Exception as e:
            print(f"   [state] Falha total ao salvar: {e}")
            return False

    def compute_hash(self, payload: dict) -> str:
        """MD5 hash dos dados relevantes (12 chars)."""
        dados = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(dados.encode()).hexdigest()[:12]

    def is_duplicate(self, state: dict, current_hash: str, today: str) -> bool:
        """True se hash igual ao anterior E mesma data."""
        if state.get("last_run_date") == today:
            print(f"   [state] Já rodou hoje ({today}).")
            return True
        if state.get("last_payload_hash") == current_hash:
            print("   [state] Payload idêntico ao último run. Nada mudou.")
            return True
        return False

    def update_mention_counts(self, state: dict, tasks: list[dict], delta: dict) -> dict:
        """Incrementa contadores para tasks ativas. Reseta para concluídas/removidas."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cooldown_ate = (datetime.now(timezone.utc) + timedelta(days=COOLDOWN_DAYS)).strftime(
            "%Y-%m-%d"
        )
        mention_counts = state.get("mention_counts", {})
        ids_cooldown = set(delta.get("em_cooldown", []))
        ids_zombies = {z["id"] for z in delta.get("zombies", [])}

        for tarefa in tasks:
            tid = tarefa["id"]
            if tid in ids_cooldown:
                continue

            mc = mention_counts.get(
                tid,
                {
                    "count": 0,
                    "first_seen": today,
                    "last_seen": today,
                    "cooldown_until": None,
                    "last_status": tarefa.get("status", ""),
                    "last_deadline": tarefa.get("deadline"),
                },
            )

            mc["count"] += 1
            mc["last_seen"] = today
            mc["last_status"] = tarefa.get("status", "")
            mc["last_deadline"] = tarefa.get("deadline")

            if tid in ids_zombies:
                mc["cooldown_until"] = cooldown_ate
                titulo = tarefa.get("titulo", "?")[:50]
                print(f"   [state] Zumbi em cooldown: {titulo} ({mc['count']}x)")

            mention_counts[tid] = mc

        state["mention_counts"] = mention_counts
        return state

    def get_zombies(self, state: dict, threshold: int = ZOMBIE_THRESHOLD) -> list[str]:
        """IDs de tasks com mention_count >= threshold."""
        mention_counts = state.get("mention_counts", {})
        return [tid for tid, mc in mention_counts.items() if mc.get("count", 0) >= threshold]

    def compute_delta(self, state: dict, current_tasks: list[dict], today: str) -> dict:
        """Compara current vs last_snapshot.

        Retorna: novas, removidas, pioraram, melhoraram, zombies, em_cooldown.
        """
        snapshot_anterior = state.get("last_snapshot", {})
        mention_counts = state.get("mention_counts", {})

        delta: dict = {
            "novas": [],
            "removidas": [],
            "pioraram": [],
            "melhoraram": [],
            "zombies": [],
            "em_cooldown": [],
        }

        current_ids = set()
        for tarefa in current_tasks:
            tid = tarefa["id"]
            current_ids.add(tid)
            anterior = snapshot_anterior.get(tid)

            if not anterior:
                delta["novas"].append(tarefa.get("titulo", "Sem título"))
            else:
                # Compara deadline
                dl_atual = tarefa.get("deadline")
                dl_ant = anterior.get("deadline")
                if dl_atual and dl_ant and dl_atual < dl_ant:
                    delta["pioraram"].append(tarefa.get("titulo", "Sem título"))

            # Verifica zombie/cooldown
            mc = mention_counts.get(tid, {})
            cooldown_until = mc.get("cooldown_until")

            if cooldown_until and cooldown_until > today:
                delta["em_cooldown"].append(tid)
            elif mc.get("count", 0) >= ZOMBIE_THRESHOLD:
                # Só é zombie se não mudou desde última vez
                mudou = tarefa.get("status") != mc.get("last_status") or tarefa.get(
                    "deadline"
                ) != mc.get("last_deadline")
                if not mudou:
                    delta["zombies"].append(
                        {
                            "id": tid,
                            "titulo": tarefa.get("titulo", "Sem título"),
                            "count": mc["count"],
                            "first_seen": mc.get("first_seen", ""),
                        }
                    )
                else:
                    # Resetou — mudou status ou deadline
                    mention_counts[tid] = {
                        **mc,
                        "count": 1,
                        "cooldown_until": None,
                    }

        # Removidas (estavam no snapshot anterior mas não mais)
        for tid in snapshot_anterior:
            if tid not in current_ids:
                delta["removidas"].append(snapshot_anterior[tid].get("titulo", "Sem título"))

        return delta

    def build_snapshot(self, tasks: list[dict]) -> dict:
        """Constrói snapshot para persistir no state."""
        return {
            t["id"]: {
                "titulo": t.get("titulo", ""),
                "status": t.get("status", ""),
                "deadline": t.get("deadline"),
                "prioridade": t.get("prioridade", ""),
            }
            for t in tasks
        }
