"""Vera Briefing — modo principal.

Pipeline: collect → analyze → context → generate → deliver.
Usa StorageBackend, LLMProvider e Domain abstratos — zero imports diretos
de Notion ou Anthropic.
"""

import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from vera.backends.base import StorageBackend
from vera.briefing_history import format_for_prompt as history_prompt
from vera.briefing_history import save_history
from vera.config import VeraConfig
from vera.domains import DOMAIN_REGISTRY
from vera.last_run import save_last_run
from vera.llm.base import LLMProvider
from vera.personas import get_persona_prompt
from vera.source_health import SourceHealthTracker
from vera.state import StateManager

# Máximo de tarefas enviadas ao LLM
MAX_TAREFAS_PROMPT = 20

# Max palavras por tipo de dia (usado nos presets de persona)
_MAX_WORDS_DIA = {0: 500, 5: 400, 6: 350}  # seg, sab, dom; default 350


# ─── Guards ──────────────────────────────────────────────────────────────────


def verificar_janela_horario(config: VeraConfig, force: bool = False) -> bool:
    """Verifica se está na janela de horário configurada."""
    if force or os.environ.get("FORCE_RUN", "").lower() == "true":
        print("   [guard] FORCE: ignorando janela de horário.")
        return True

    tz = ZoneInfo(config.timezone)
    agora = datetime.now(tz)
    hora_briefing = config.schedule.briefing
    try:
        hora_min = int(hora_briefing.split(":")[0]) - 3  # 3h antes
        hora_max = int(hora_briefing.split(":")[0]) + 2  # 2h depois
        hora_min = max(0, hora_min)
        hora_max = min(23, hora_max)
    except (ValueError, IndexError):
        hora_min, hora_max = 6, 11

    if not (hora_min <= agora.hour <= hora_max):
        print(
            f"   [guard] Fora da janela ({agora.hour}h). "
            f"Briefing roda entre {hora_min}h–{hora_max}h."
        )
        return False
    return True


# ─── Scoring e ranking ───────────────────────────────────────────────────────


def score_tarefa(tarefa: dict, mention_counts: dict) -> float:
    """Calcula score de prioridade para ranking."""
    score = 0.0
    tid = tarefa["id"]

    # Deadline
    deadline = tarefa.get("deadline")
    if deadline:
        hoje = datetime.now().strftime("%Y-%m-%d")
        if deadline < hoje:
            score += 100  # Atrasada
        elif deadline == hoje:
            score += 80  # Hoje

    # Prioridade (genérica — funciona com qualquer label)
    prio = (tarefa.get("prioridade") or "").lower()
    if any(p in prio for p in ["alta", "high", "crítico", "crítica", "urgent"]):
        score += 30
    elif any(p in prio for p in ["média", "medium", "importante"]):
        score += 15

    # Mention count: reduz score para tarefas muito repetidas
    count = mention_counts.get(tid, {}).get("count", 0)
    score -= min(count * 3, 30)

    return score


def filtrar_e_rankear(tarefas: list[dict], state: dict, delta: dict) -> list[dict]:
    """Filtra zombies/cooldown e rankeia por score."""
    mention_counts = state.get("mention_counts", {})
    ids_cooldown = set(delta.get("em_cooldown", []))
    ids_zombies = {z["id"] for z in delta.get("zombies", [])}

    ativas = [t for t in tarefas if t["id"] not in ids_cooldown and t["id"] not in ids_zombies]

    for t in ativas:
        t["_score"] = score_tarefa(t, mention_counts)

    ativas.sort(key=lambda x: x["_score"], reverse=True)
    return ativas[:MAX_TAREFAS_PROMPT]


# ─── Workspace files ────────────────────────────────────────────────────────


def carregar_workspace_files(config: VeraConfig) -> dict:
    """Carrega AGENT.md e USER.md do workspace/.

    Fallback: se arquivo nao existe, tenta .example.
    Custom persona file sobrescreve AGENT.md.
    """
    workspace_path = Path("workspace")
    arquivos = {}

    for nome in ["USER.md", "AGENT.md"]:
        caminho = workspace_path / nome
        if caminho.exists():
            conteudo = caminho.read_text(encoding="utf-8").strip()
            if conteudo:
                arquivos[nome] = conteudo[:1500]
        else:
            # Tenta .example como fallback
            example_name = nome.replace(".md", ".example.md")
            example_path = workspace_path / example_name
            if example_path.exists():
                conteudo = example_path.read_text(encoding="utf-8").strip()
                if conteudo:
                    arquivos[nome] = conteudo[:1500]

    # Custom persona file sobrescreve AGENT.md
    if config.persona.custom_prompt_file:
        custom_path = Path(config.persona.custom_prompt_file)
        if custom_path.exists():
            arquivos["AGENT.md"] = custom_path.read_text(encoding="utf-8").strip()[:1500]

    return arquivos


def _get_system_prompt(config: VeraConfig, workspace: dict, dia_num: int = 2) -> str:
    """Monta system prompt a partir do preset ou custom.

    Se AGENT.md existe e preset e "custom", usa AGENT.md.
    Senao, usa preset do personas.py com max_words por dia.
    Se USER.md existe, injeta como secao sobre o usuario.
    """
    max_words = _MAX_WORDS_DIA.get(dia_num, 350)

    if config.persona.preset == "custom" and workspace.get("AGENT.md"):
        prompt = workspace["AGENT.md"]
    else:
        prompt = get_persona_prompt(config.persona.preset, config.name, max_words)

    # Injeta USER.md se existe
    if workspace.get("USER.md"):
        prompt += f"\n\n=== SOBRE O USUARIO ===\n{workspace['USER.md']}"

    return prompt


# ─── Contexto para o LLM ────────────────────────────────────────────────────


def montar_contexto(
    tarefas_rankeadas: list[dict],
    delta: dict,
    zombies: list[dict],
    domain_contexts: dict[str, str],
    mention_counts: dict,
    workspace: dict,
    today: str,
    dia_semana_num: int,
) -> str:
    """Monta contexto estruturado para o LLM."""
    ctx = f"DATA: {today}\n\n"

    if workspace.get("USER.md"):
        ctx += f"=== PERFIL ===\n{workspace['USER.md']}\n\n"

    # Delta
    if delta.get("novas"):
        ctx += "=== ENTRARAM NO RADAR HOJE ===\n"
        ctx += "\n".join(f"- {n}" for n in delta["novas"][:5]) + "\n\n"

    if delta.get("pioraram"):
        ctx += "=== PIORARAM DESDE ONTEM ===\n"
        ctx += "\n".join(f"- {n}" for n in delta["pioraram"][:3]) + "\n\n"

    # Tarefas rankeadas com mention_counts
    if tarefas_rankeadas:
        ctx += f"=== TAREFAS PRIORITÁRIAS ({len(tarefas_rankeadas)}) ===\n"
        for t in tarefas_rankeadas:
            deadline_str = f" | deadline: {t['deadline']}" if t.get("deadline") else ""
            prio_str = f" | {t['prioridade']}" if t.get("prioridade") else ""
            tid = t["id"]
            count = mention_counts.get(tid, {}).get("count", 0)
            if count >= 4:
                mc_str = f" | citada {count}x"
            elif count >= 2:
                mc_str = f" | ({count}x)"
            else:
                mc_str = ""
            ctx += f"- {t['titulo']} ({t['status']}{deadline_str}{prio_str}{mc_str})\n"
        ctx += "\n"

    # Zombies
    if zombies:
        ctx += "=== TAREFAS ZUMBI (precisam de decisão) ===\n"
        for z in zombies[:5]:
            ctx += f"- {z['titulo']} — citada {z['count']}x desde {z['first_seen']}\n"
        ctx += "Opções: arquivar / redefinir deadline / quebrar em subtarefas\n\n"

    # Contextos dos domínios (pipeline, contacts, etc.)
    for domain_name, domain_ctx in domain_contexts.items():
        if domain_ctx.strip():
            ctx += f"{domain_ctx}\n\n"

    # Histórico de briefings (anti-repetição)
    hist = history_prompt()
    if hist:
        ctx += hist + "\n"

    return ctx.strip()


def montar_contexto_sabado(
    tarefas_rankeadas: list[dict],
    delta: dict,
    zombies: list[dict],
    domain_contexts: dict[str, str],
    mention_counts: dict,
    today: str,
) -> str:
    """Contexto específico para retrospectiva de sábado."""
    mc = mention_counts

    top_abertas = []
    for t in tarefas_rankeadas[:5]:
        count = mc.get(t["id"], {}).get("count", 0)
        mc_str = f" ({count}x)" if count >= 2 else ""
        top_abertas.append(f"{t['titulo']}{mc_str}")

    zombies_fmt = f"{len(zombies)} tarefas zumbi" if zombies else "sem zumbis"

    ctx = (
        f"DATA: {today} (Sábado — retrospectiva semanal)\n\n"
        f"ABERTAS PRIORITÁRIAS ({len(tarefas_rankeadas)}):\n"
        + ("\n".join(f"- {t}" for t in top_abertas) if top_abertas else "- Nenhuma")
        + f"\n\nZUMBIS: {zombies_fmt}"
    )

    # Domínios
    for domain_name, domain_ctx in domain_contexts.items():
        if domain_ctx.strip():
            ctx += f"\n\n{domain_ctx}"

    hist = history_prompt()
    if hist:
        ctx += f"\n\n{hist}"

    return ctx


def montar_contexto_domingo(
    tarefas_rankeadas: list[dict],
    zombies: list[dict],
    domain_contexts: dict[str, str],
    mention_counts: dict,
    today: str,
) -> str:
    """Contexto específico para planejamento de domingo."""
    mc = mention_counts
    hoje_date = datetime.strptime(today, "%Y-%m-%d").date()
    proxima_semana = hoje_date + timedelta(days=7)

    urgentes_semana = []
    deadlines_count = 0
    for t in tarefas_rankeadas:
        count = mc.get(t["id"], {}).get("count", 0)
        mc_str = f" ({count}x)" if count >= 2 else ""
        dl = t.get("deadline")
        dl_str = ""
        if dl:
            try:
                dl_date = datetime.strptime(dl[:10], "%Y-%m-%d").date()
                if dl_date <= proxima_semana:
                    deadlines_count += 1
                    dias_restantes = (dl_date - hoje_date).days
                    if dias_restantes <= 0:
                        dl_str = " [VENCIDA]"
                    elif dias_restantes <= 2:
                        dl_str = f" [deadline em {dias_restantes}d]"
                    else:
                        dl_str = f" [deadline {dl[:10]}]"
            except (ValueError, TypeError):
                pass
        urgentes_semana.append(f"{t['titulo']}{mc_str}{dl_str}")
        if len(urgentes_semana) >= 5:
            break

    ctx = (
        f"DATA: {today} (Domingo — planejamento estratégico)\n\n"
        f"SEMANA QUE VEM: {deadlines_count} deadlines | "
        f"{len(tarefas_rankeadas)} tarefas abertas | {len(zombies)} zumbis\n\n"
        f"TOP 5 PRIORIDADES:\n"
        + ("\n".join(f"- {t}" for t in urgentes_semana) if urgentes_semana else "- Nenhuma urgente")
    )

    for domain_name, domain_ctx in domain_contexts.items():
        if domain_ctx.strip():
            ctx += f"\n\n{domain_ctx}"

    hist = history_prompt()
    if hist:
        ctx += f"\n\n{hist}"

    return ctx


# ─── Geração via LLM ────────────────────────────────────────────────────────

_DIAS_SEMANA = {
    0: "Segunda",
    1: "Terça",
    2: "Quarta",
    3: "Quinta",
    4: "Sexta",
    5: "Sábado",
    6: "Domingo",
}

_MESES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

_INSTRUCOES_DIA = {
    0: "Segunda: overview da semana passada (1-2 linhas) + setup da semana.",
    1: "Terça: foco no dia. Sem retrospectiva.",
    2: "Quarta: meio de semana. Verifica se o ritmo está mantido.",
    3: "Quinta: olho no que fecha até sexta. Tom: urgência construtiva.",
    4: "Sexta: fecha o que pode. Avisa o que passa pra próxima semana sem drama.",
}

_REGRAS_TOM = """
REGRAS DE TOM POR CONTAGEM DE MENÇÕES:
- 1x (sem anotação): primeira vez, tom normal
- 2-3x (citada Nx): tom normal, cita se relevante
- 4-6x: PARA DE ESCALAR TOM. Oferece 2-3 ações concretas para desbloquear.
  Ex: "[Tarefa X] há 2 semanas. Opções: (1) quebrar menor, (2) delegar, (3) arquivar."
- 7x ou mais: "vou parar de mencionar [X] até você me dizer o que fazer com ela"
"""


async def gerar_briefing(
    llm: LLMProvider,
    system_prompt: str,
    contexto: str,
    dia_num: int,
    cabecalho: str,
    config: VeraConfig,
) -> str:
    """Gera briefing via LLM."""

    if dia_num == 5:
        # Sábado: retrospectiva
        user_prompt = f"""INSTRUÇÃO: É sábado. Gere um relatório semanal honesto.
Estrutura:
1. O que ficou aberto e por que importa na semana que vem
2. Uma observação cirúrgica sobre o padrão da semana
3. Encerramento que prepare o domingo

REGRAS:
- Máximo 400 palavras. Prosa corrida.
- Tom analítico com pitada de ironia — não punitivo
- Sem despedidas genéricas
{_REGRAS_TOM}

CONTEXTO:
{contexto}

Gere o relatório começando com:
{cabecalho}"""

    elif dia_num == 6:
        # Domingo: planejamento
        user_prompt = f"""INSTRUÇÃO: É domingo. Dia de planejamento estratégico, não de cobrança.
Estrutura obrigatória:
1. Panorama da semana: quantos deadlines, follow-ups pendentes
2. Sugira 3 prioridades concretas pra segunda-feira (baseadas nos dados)
3. Encerra com o que vai determinar se a semana foi boa ou não

REGRAS:
- Máximo 350 palavras. Tom estratégico, não motivacional.
- Sem "você consegue!" ou elogios genéricos.
{_REGRAS_TOM}

CONTEXTO:
{contexto}

Gere o planejamento começando com:
{cabecalho}"""

    else:
        # Weekday
        instrucao = _INSTRUCOES_DIA.get(dia_num, "Foco operacional.")
        max_palavras = 500 if dia_num == 0 else 350

        user_prompt = f"""INSTRUÇÃO DO DIA: {instrucao}

CONTEXTO (já filtrado e priorizado — não invente nada além disto):
{contexto}

REGRAS INEGOCIÁVEIS:
- Máximo {max_palavras} palavras
- Prosa corrida; bullets só em listas de 3+ itens
- Máximo 3 termos em **bold** por mensagem
- Zumbis: menciona com "precisam de uma decisão", não com cobrança
- Não mencione tarefas que não estejam no contexto acima
- Não invente eventos, deadlines ou dados
- Termine com despedida curta e contextual (não genérica)
{_REGRAS_TOM}

EQUILÍBRIO POSITIVO:
- O briefing não é só cobrança: é um balanço honesto entre o que avançou e o que trava

Gere o briefing começando com:
{cabecalho}"""

    max_tokens = 800 if dia_num == 0 else 700

    try:
        return await llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=0.7,
        )
    except Exception as e:
        return f"{cabecalho}\n\nErro técnico: {str(e)[:200]}"


# ─── Pipeline principal ─────────────────────────────────────────────────────


async def run_async(
    config: VeraConfig,
    backend: StorageBackend,
    llm: LLMProvider,
    force: bool = False,
    dry_run: bool = False,
) -> str | None:
    """Pipeline completo do briefing (async)."""
    tz = ZoneInfo(config.timezone)
    agora = datetime.now(tz)
    hoje = agora.strftime("%Y-%m-%d")
    dia_num = agora.weekday()

    cabecalho = f"VERA — {_DIAS_SEMANA[dia_num]}, {agora.day}/{_MESES[agora.month]}"

    print("=" * 60)
    print("   VERA v0.2 — Briefing")
    print("=" * 60)
    print(f"   {agora.strftime('%d/%m/%Y %H:%M')} ({config.timezone})")

    # Guard 1: janela de horário
    if not verificar_janela_horario(config, force):
        return None

    # State
    print("\n   Carregando state...")
    state_mgr = StateManager()
    state = state_mgr.load()

    # Collect: domínios habilitados
    print("\n   Coletando dados dos domínios...")
    t0 = time.monotonic()

    domain_instances = {}
    domain_data = {}
    domain_analyses = {}
    domain_contexts = {}

    for domain_name, domain_cfg in config.domains.items():
        if not domain_cfg.enabled:
            continue

        domain_cls = DOMAIN_REGISTRY.get(domain_name)
        if not domain_cls:
            print(f"   [skip] Domínio '{domain_name}' não registrado")
            continue

        domain = domain_cls(domain_cfg.model_dump(), backend)
        domain_instances[domain_name] = domain

        try:
            data = await domain.collect()
            domain_data[domain_name] = data
            analysis = domain.analyze(data)
            domain_analyses[domain_name] = analysis
            ctx = domain.context(data, analysis)
            domain_contexts[domain_name] = ctx

            # Log
            if domain_name == "tasks":
                print(f"   [tasks] {analysis.get('total', 0)} tarefas ativas")
            elif ctx.strip():
                print(f"   [{domain_name}] {ctx.split(chr(10))[0][:60]}")
        except Exception as e:
            print(f"   [erro] Domínio '{domain_name}': {e}")
            domain_data[domain_name] = {}
            domain_analyses[domain_name] = {}
            domain_contexts[domain_name] = ""

    elapsed = time.monotonic() - t0
    print(f"   Dados coletados em {elapsed:.1f}s")

    # Tasks são obrigatórias
    tarefas = domain_data.get("tasks", {}).get("tarefas", [])
    if not tarefas:
        print("   [aviso] Nenhuma tarefa encontrada. Briefing pode ser vazio.")

    # Workspace files
    print("   Carregando workspace...")
    workspace = carregar_workspace_files(config)
    print(f"   Carregados: {list(workspace.keys())}")

    # Calendar (opcional)
    calendar_events = []
    calendar_ctx = ""
    if _calendar_habilitado(config):
        try:
            from vera.integrations.calendar import formatar_eventos_para_contexto

            calendar_events = await _buscar_eventos_calendar(config)
            calendar_ctx = formatar_eventos_para_contexto(calendar_events)
            if calendar_events:
                print(f"   [calendar] {len(calendar_events)} evento(s)")
        except Exception as e:
            print(f"   [calendar] Erro: {e}")

    # Source health alerts
    source_health_ctx = ""
    try:
        tracker = SourceHealthTracker()
        source_health_ctx = tracker.format_for_briefing()
        if source_health_ctx:
            print("   [source_health] Alertas detectados")
    except Exception:
        pass

    # Guard 2: idempotência
    payload_for_hash = {
        "tarefas": sorted([t.get("titulo", "") for t in tarefas]),
        "domains": sorted(
            [(name, str(analysis)) for name, analysis in domain_analyses.items() if name != "tasks"]
        ),
    }
    payload_hash = state_mgr.compute_hash(payload_for_hash)

    if not force and state_mgr.is_duplicate(state, payload_hash, hoje):
        print("   Abortando (idempotência). Use --force para ignorar.")
        return None

    # Delta e contadores
    print("\n   Calculando delta e contadores...")
    delta = state_mgr.compute_delta(state, tarefas, hoje)
    state = state_mgr.update_mention_counts(state, tarefas, delta)
    zombies = delta.get("zombies", [])
    mention_counts = state.get("mention_counts", {})

    print(
        f"   Novas: {len(delta['novas'])} | "
        f"Pioraram: {len(delta['pioraram'])} | "
        f"Zumbis: {len(zombies)} | "
        f"Cooldown: {len(delta['em_cooldown'])}"
    )

    # Filtra e rankeia
    print("\n   Filtrando e rankeando...")
    tarefas_rankeadas = filtrar_e_rankear(tarefas, state, delta)
    print(f"   {len(tarefas_rankeadas)} tarefas enviadas ao LLM")

    # Research Packs (RADAR section)
    research_ctx = ""
    if _research_habilitado(config):
        try:
            research_ctx = await _executar_research_packs(config, llm)
            if research_ctx:
                print("   [research] RADAR section gerada")
        except Exception as e:
            print(f"   [research] Erro: {e}")

    # Injeta calendar, source health e research nos domain_contexts
    if calendar_ctx:
        domain_contexts["_calendar"] = calendar_ctx
    if source_health_ctx:
        domain_contexts["_source_health"] = source_health_ctx
    if research_ctx:
        domain_contexts["_research"] = research_ctx

    # Monta contexto por dia da semana
    if dia_num == 5:
        contexto = montar_contexto_sabado(
            tarefas_rankeadas,
            delta,
            zombies,
            domain_contexts,
            mention_counts,
            hoje,
        )
    elif dia_num == 6:
        contexto = montar_contexto_domingo(
            tarefas_rankeadas,
            zombies,
            domain_contexts,
            mention_counts,
            hoje,
        )
    else:
        contexto = montar_contexto(
            tarefas_rankeadas,
            delta,
            zombies,
            domain_contexts,
            mention_counts,
            workspace,
            hoje,
            dia_num,
        )

    # Gera briefing via LLM
    print("\n   Gerando briefing via LLM...")
    system_prompt = _get_system_prompt(config, workspace, dia_num)

    mensagem = await gerar_briefing(
        llm,
        system_prompt,
        contexto,
        dia_num,
        cabecalho,
        config,
    )

    print("\n" + "=" * 60)
    print(mensagem)
    print("=" * 60)

    # Persiste
    if not dry_run:
        # Atualiza state
        state["last_run_date"] = hoje
        state["last_payload_hash"] = payload_hash
        state["last_snapshot"] = state_mgr.build_snapshot(tarefas)
        state["briefing_count"] = state.get("briefing_count", 0) + 1
        state_mgr.save(state)

        # Salva histórico
        save_history(mensagem)

        # Observabilidade
        mc = state.get("mention_counts", {})
        high_mc = {k: v["count"] for k, v in mc.items() if v.get("count", 0) >= 4}
        domains_active = [n for n, c in config.domains.items() if c.enabled]
        domains_skipped = [n for n, c in config.domains.items() if not c.enabled]
        duration = time.monotonic() - t0

        save_last_run(
            "briefing",
            {
                "domains_active": domains_active,
                "domains_skipped": domains_skipped,
                "tasks_total": len(tarefas),
                "tasks_in_briefing": len(tarefas_rankeadas),
                "zombies": len(zombies),
                "cooldown": len(delta.get("em_cooldown", [])),
                "delta": {
                    "novas": len(delta.get("novas", [])),
                    "removidas": len(delta.get("removidas", [])),
                    "pioraram": len(delta.get("pioraram", [])),
                },
                "mention_counts_high": high_mc,
                "calendar_events": len(calendar_events),
                "llm_provider": config.llm.default,
                "idempotent_skip": False,
                "duration_seconds": round(duration, 1),
                "source_health_alerts": (
                    SourceHealthTracker().get_alerts() if source_health_ctx else []
                ),
                "payload_hash": payload_hash,
                "errors": [],
            },
        )
    else:
        print("\n   DRY RUN — não salvou state nem enviou Telegram.")

    print("\n   VERA BRIEFING FINALIZADO!\n")
    return mensagem


def _calendar_habilitado(config: VeraConfig) -> bool:
    """Verifica se calendar esta habilitado no config."""
    integrations = getattr(config, "integrations", None)
    if not integrations:
        return False
    gcal = getattr(integrations, "google_calendar", None)
    return bool(gcal and gcal.enabled)


async def _buscar_eventos_calendar(config: VeraConfig) -> list[dict]:
    """Busca eventos do Google Calendar se configurado."""
    from vera.integrations.calendar import GoogleCalendarProvider

    gcal_cfg = config.integrations.google_calendar
    credentials = os.environ.get(gcal_cfg.credentials_env, "")
    if not credentials:
        return []

    provider = GoogleCalendarProvider(
        credentials_json=credentials,
        calendar_ids=gcal_cfg.calendar_ids,
    )
    return await provider.get_events_today(config.timezone)


def _research_habilitado(config: VeraConfig) -> bool:
    """Verifica se research esta habilitado no config."""
    research = getattr(config, "research", None)
    if not research:
        return False
    return bool(research.enabled and research.packs)


async def _executar_research_packs(config: VeraConfig, llm: LLMProvider) -> str:
    """Executa packs de research habilitados e retorna contexto RADAR."""
    from pathlib import Path

    from vera.research.dedup import DedupEngine
    from vera.research.registry import registry

    registry.discover()
    parts = []

    for pack_name, pack_cfg in config.research.packs.items():
        if not pack_cfg.enabled:
            continue

        pack_cls = registry.get(pack_name)
        if not pack_cls:
            continue

        try:
            # Carrega pack config
            pack_config = _load_pack_config_for_briefing(pack_cfg.config_path, pack_name)
            pack_instance = pack_cls()

            # Collect
            items = await pack_instance.collect(pack_config)
            if not items:
                continue

            # Dedup
            dedup_ttl = pack_config.get("dedup", {}).get("ttl_days", 30)
            dedup = DedupEngine(Path(f"state/dedup/{pack_name}.json"), default_ttl_days=dedup_ttl)
            new_items = dedup.filter_new(items)
            if not new_items:
                continue

            # Score
            scored = await pack_instance.score(new_items, pack_config)
            threshold = pack_config.get("scoring", {}).get("relevance_threshold", 0.5)
            relevant = [i for i in scored if i.score >= threshold]
            if not relevant:
                continue

            # Format for briefing
            from datetime import datetime, timezone

            from vera.research.base import ResearchResult

            result = ResearchResult(
                pack_name=pack_name,
                items=relevant,
                new_count=len(relevant),
                total_checked=len(items),
                sources_checked=0,
                sources_failed=[],
                timestamp=datetime.now(timezone.utc),
            )
            formatted = pack_instance.format_for_briefing(result)
            if formatted:
                parts.append(formatted)

            # Save dedup state
            dedup.mark_items(new_items, dedup_ttl)
            dedup.save()

        except Exception as e:
            print(f"   [research] Pack '{pack_name}' erro: {e}")

    if not parts:
        return ""

    return "=== RADAR ===\n" + "\n\n".join(parts)


def _load_pack_config_for_briefing(config_path: str, pack_name: str) -> dict:
    """Carrega config de pack para uso no briefing."""
    from pathlib import Path

    import yaml as _yaml

    if config_path:
        p = Path(config_path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return _yaml.safe_load(f) or {}

    for candidate in [
        Path(f"config/packs/{pack_name}.yaml"),
        Path(f"config/packs/{pack_name}.example.yaml"),
    ]:
        if candidate.exists():
            with open(candidate, encoding="utf-8") as f:
                return _yaml.safe_load(f) or {}

    return {}


def run(
    config: VeraConfig,
    backend: StorageBackend,
    llm: LLMProvider,
    force: bool = False,
    dry_run: bool = False,
) -> str | None:
    """Entrypoint sincrono."""
    return asyncio.run(run_async(config, backend, llm, force=force, dry_run=dry_run))
