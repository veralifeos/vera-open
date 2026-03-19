"""Vera CLI — interface Typer com subcommands."""

import asyncio
import logging
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

# Carrega .env automaticamente (busca no cwd e diretório pai)
# encoding="utf-8-sig" ignora BOM se presente (comum em Windows)
load_dotenv(encoding="utf-8-sig")
load_dotenv(Path("config/.env"), encoding="utf-8-sig")

from vera import __version__

app = typer.Typer(
    name="vera",
    help="Vera — AI-native Life Operating System.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"Vera v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Exibe a versão e sai.",
    ),
) -> None:
    """Vera — AI-native Life Operating System."""


# ─── Briefing ────────────────────────────────────────────────────────────────


@app.command()
def briefing(
    force: bool = typer.Option(
        False, "--force", "-f", help="Ignora janela de horário e idempotência."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Executa sem enviar Telegram nem gravar state."
    ),
    weekly: bool = typer.Option(
        False, "--weekly", "-w", help="Relatório semanal com retrospectiva e métricas."
    ),
) -> None:
    """Gera e envia o briefing diário (ou semanal com --weekly)."""
    from vera.config import load_config
    from vera.modes.briefing import run

    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Erro ao carregar config: {e}")
        raise typer.Exit(code=1)

    # Cria backend
    try:
        backend = _create_backend(config)
    except Exception as e:
        typer.echo(f"Erro ao criar backend: {e}")
        raise typer.Exit(code=1)

    # Cria LLM provider
    try:
        llm = _create_llm_provider(config, config.llm.default)
    except Exception as e:
        typer.echo(f"Erro ao criar LLM provider: {e}")
        raise typer.Exit(code=1)

    # Dry run também vem do config
    effective_dry_run = dry_run or config.debug.dry_run

    try:
        resultado = run(config, backend, llm, force=force, dry_run=effective_dry_run, weekly=weekly)

        # Envia no Telegram se nao dry_run
        if resultado and not effective_dry_run:
            _enviar_telegram(config, resultado)

    except Exception as e:
        typer.echo(f"Erro critico: {e}")
        if not effective_dry_run:
            _notificar_erro_telegram(config, f"{type(e).__name__}: {str(e)[:200]}")
        raise typer.Exit(code=1)


# ─── Research ─────────────────────────────────────────────────────────────────


@app.command()
def research(
    pack: str = typer.Argument(
        None, help="Nome do pack (news, jobs, financial). Omitir com --list ou --all."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Executa sem gravar state."),
    force: bool = typer.Option(False, "--force", "-f", help="Ignorar dedup."),
    list_packs: bool = typer.Option(False, "--list", help="Listar packs disponíveis."),
    all_packs: bool = typer.Option(False, "--all", help="Executar todos os packs em paralelo."),
) -> None:
    """Executa um Research Pack (news, jobs, financial)."""
    from vera.research.registry import registry

    # Auto-discover packs
    registry.discover()

    if list_packs:
        available = registry.list_available()
        if available:
            typer.echo("Packs disponíveis:")
            for name in available:
                pack_cls = registry.get(name)
                desc = getattr(pack_cls, "description", "") if pack_cls else ""
                typer.echo(f"  - {name}: {desc}")
        else:
            typer.echo("Nenhum pack disponível.")
        return

    if all_packs:
        available = registry.list_available()
        if not available:
            typer.echo("Nenhum pack disponível.")
            raise typer.Exit(code=1)

        from vera.config import load_config

        try:
            config = load_config()
        except (FileNotFoundError, ValueError) as e:
            typer.echo(f"Erro ao carregar config: {e}")
            raise typer.Exit(code=1)

        try:
            llm = _create_llm_provider(config, config.llm.default)
        except Exception as e:
            typer.echo(f"Erro ao criar LLM provider: {e}")
            raise typer.Exit(code=1)

        try:
            results = asyncio.run(
                _run_all_research_packs(
                    available, registry, config, llm, dry_run=dry_run, force=force
                )
            )

            typer.echo(f"\n{'=' * 40}")
            typer.echo("RESEARCH — Resumo")
            typer.echo(f"{'=' * 40}")
            for pack_name, result in results.items():
                if isinstance(result, Exception):
                    typer.echo(f"  {pack_name}: ERRO — {result}")
                elif result:
                    typer.echo(
                        f"  {result.pack_name}: {result.new_count} novos de "
                        f"{result.total_checked} verificados"
                    )
                    if result.sources_failed:
                        typer.echo(f"    Fontes com erro: {result.sources_failed}")
                else:
                    typer.echo(f"  {pack_name}: sem resultados")
        except Exception as e:
            typer.echo(f"Erro ao executar packs: {e}")
            raise typer.Exit(code=1)
        return

    if not pack:
        typer.echo("Especifique um pack, use --list ou --all. Ex: vera research news")
        raise typer.Exit(code=1)

    pack_cls = registry.get(pack)
    if not pack_cls:
        available = registry.list_available()
        typer.echo(f"Pack '{pack}' não encontrado. Disponíveis: {available}")
        raise typer.Exit(code=1)

    # Carrega config principal
    from vera.config import load_config

    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Erro ao carregar config: {e}")
        raise typer.Exit(code=1)

    # Carrega pack config
    pack_config = _load_pack_config(pack, config)

    # Cria LLM provider para synthesis
    try:
        llm = _create_llm_provider(config, config.llm.default)
    except Exception as e:
        typer.echo(f"Erro ao criar LLM provider: {e}")
        raise typer.Exit(code=1)

    # Executa pipeline do pack
    try:
        result = asyncio.run(
            _run_research_pack(pack_cls, pack_config, llm, dry_run=dry_run, force=force)
        )
        if result:
            typer.echo(
                f"\n{result.pack_name}: {result.new_count} novos de "
                f"{result.total_checked} verificados "
                f"({result.sources_checked} fontes)"
            )
            if result.sources_failed:
                typer.echo(f"  Fontes com erro: {result.sources_failed}")
            if result.synthesis:
                typer.echo(f"\n{result.synthesis}")
    except Exception as e:
        typer.echo(f"Erro no pack '{pack}': {e}")
        raise typer.Exit(code=1)


async def _run_research_pack(pack_cls, pack_config, llm, dry_run=False, force=False):
    """Executa pipeline completo de um research pack."""
    from datetime import datetime, timezone
    from pathlib import Path

    from vera.research.base import ResearchResult
    from vera.research.dedup import DedupEngine
    from vera.research.synthesis import SynthesisEngine

    pack_instance = pack_cls()
    pack_name = pack_instance.name

    print(f"\n   RESEARCH: {pack_name}")
    print("=" * 40)

    # 1. Collect
    print("   Coletando...")
    items = await pack_instance.collect(pack_config)
    total_checked = len(items)
    print(f"   {total_checked} items coletados")

    # 2. Dedup
    dedup_ttl = pack_config.get("dedup", {}).get("ttl_days", 30)
    dedup_path = Path(f"state/dedup/{pack_name}.json")
    dedup = DedupEngine(dedup_path, default_ttl_days=dedup_ttl)

    if force:
        new_items = items
        print(f"   --force: ignorando dedup ({len(items)} items)")
    else:
        new_items = dedup.filter_new(items)
        print(f"   {len(new_items)} novos (dedup filtrou {total_checked - len(new_items)})")

    # 3. Score
    if new_items:
        print("   Scoring...")
        scored_items = await pack_instance.score(new_items, pack_config)
    else:
        scored_items = []

    # 4. Filter by threshold
    threshold = pack_config.get("scoring", {}).get("relevance_threshold", 0.5)
    relevant = [i for i in scored_items if i.score >= threshold]
    print(f"   {len(relevant)} acima do threshold ({threshold})")

    # 5. Synthesize
    synthesis_text = ""
    if relevant:
        print("   Sintetizando...")
        engine = SynthesisEngine(llm)
        # Agrupa por topico
        topics: dict[str, list] = {}
        for item in relevant:
            t = item.topic or "Geral"
            topics.setdefault(t, []).append(item)

        max_words = pack_config.get("synthesis", {}).get("max_words_per_topic", 80)
        synthesis_text = await engine.synthesize_pack(
            ResearchResult(
                pack_name=pack_name,
                items=relevant,
                new_count=len(relevant),
                total_checked=total_checked,
                sources_checked=0,
                sources_failed=[],
                timestamp=datetime.now(timezone.utc),
            ),
            topics,
            max_words_per_topic=max_words,
        )

    # 6. Persist dedup
    if not dry_run and new_items:
        dedup.mark_items(new_items, dedup_ttl)
        dedup.cleanup_expired()
        dedup.save()
        print("   State salvo.")
    elif dry_run:
        print("   DRY RUN — state não salvo.")

    return ResearchResult(
        pack_name=pack_name,
        items=relevant,
        new_count=len(relevant),
        total_checked=total_checked,
        sources_checked=0,
        sources_failed=[],
        timestamp=datetime.now(timezone.utc),
        synthesis=synthesis_text,
    )


async def _run_all_research_packs(available, registry, config, llm, dry_run=False, force=False):
    """Executa todos os packs disponíveis em paralelo."""
    coros = {}
    for pack_name in available:
        pack_cls = registry.get(pack_name)
        if not pack_cls:
            continue
        pack_config = _load_pack_config(pack_name, config)
        coros[pack_name] = _run_research_pack(
            pack_cls, pack_config, llm, dry_run=dry_run, force=force
        )

    results = {}
    gathered = await asyncio.gather(*coros.values(), return_exceptions=True)
    for pack_name, result in zip(coros.keys(), gathered):
        results[pack_name] = result

    return results


def _load_pack_config(pack_name: str, config) -> dict:
    """Carrega config de um pack (YAML separado)."""
    import yaml as _yaml

    # Tenta path do config principal
    research_cfg = getattr(config, "research", None)
    if research_cfg and research_cfg.packs:
        pack_cfg = research_cfg.packs.get(pack_name)
        if pack_cfg and pack_cfg.config_path:
            cfg_path = Path(pack_cfg.config_path)
            if cfg_path.exists():
                with open(cfg_path, encoding="utf-8") as f:
                    return _yaml.safe_load(f) or {}

    # Fallback: config/packs/{pack_name}.yaml
    for candidate in [
        Path(f"config/packs/{pack_name}.yaml"),
        Path(f"config/packs/{pack_name}.example.yaml"),
    ]:
        if candidate.exists():
            with open(candidate, encoding="utf-8") as f:
                return _yaml.safe_load(f) or {}

    return {}


# ─── Status ──────────────────────────────────────────────────────────────────


@app.command()
def status() -> None:
    """Mostra status do sistema: último run, saúde das fontes, métricas."""
    import json

    from vera.last_run import LAST_RUN_PATH
    from vera.source_health import SourceHealthTracker
    from vera.state import StateManager

    typer.echo("=" * 50)
    typer.echo("  VERA — Status do Sistema")
    typer.echo("=" * 50)

    # 1. Último briefing
    typer.echo("\n  Briefing:")
    state_mgr = StateManager()
    state_path = state_mgr.state_path
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            last_run = state.get("last_run_date", "nunca")
            briefing_count = state.get("briefing_count", 0)
            mc = state.get("mention_counts", {})
            zombies = sum(1 for v in mc.values() if v.get("count", 0) >= 8)
            cooldowns = sum(1 for v in mc.values() if v.get("cooldown_until"))
            typer.echo(f"    Último run: {last_run}")
            typer.echo(f"    Briefings gerados: {briefing_count}")
            typer.echo(f"    Tarefas rastreadas: {len(mc)}")
            typer.echo(f"    Zombies: {zombies} | Cooldown: {cooldowns}")
        except Exception as e:
            typer.echo(f"    Erro ao ler state: {e}")
    else:
        typer.echo("    Nenhum state encontrado (primeira execução?)")

    # 2. Último run (observabilidade)
    typer.echo("\n  Última execução:")
    if LAST_RUN_PATH.exists():
        try:
            last_run_data = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
            for mode, info in last_run_data.items():
                ts = info.get("timestamp", "?")[:19]
                duration = info.get("duration_seconds", "?")
                typer.echo(f"    [{mode}] {ts} ({duration}s)")
                if mode == "briefing":
                    tasks_total = info.get("tasks_total", "?")
                    tasks_in = info.get("tasks_in_briefing", "?")
                    llm = info.get("llm_provider", "?")
                    typer.echo(f"      Tarefas: {tasks_in}/{tasks_total} enviadas ao LLM ({llm})")
        except Exception as e:
            typer.echo(f"    Erro ao ler last_run: {e}")
    else:
        typer.echo("    Nenhum registro de execução")

    # 3. Research packs (dedup state)
    typer.echo("\n  Research Packs:")
    dedup_dir = Path("state/dedup")
    if dedup_dir.exists():
        for dedup_file in sorted(dedup_dir.glob("*.json")):
            try:
                dedup_data = json.loads(dedup_file.read_text(encoding="utf-8"))
                items = dedup_data.get("items", {})
                pack_name = dedup_file.stem
                typer.echo(f"    [{pack_name}] {len(items)} itens no dedup")
            except Exception:
                typer.echo(f"    [{dedup_file.stem}] erro ao ler")
    else:
        typer.echo("    Nenhum pack executado ainda")

    # 4. Source health
    typer.echo("\n  Saúde das fontes:")
    tracker = SourceHealthTracker()
    alerts = tracker.get_alerts()
    if alerts:
        for source in alerts:
            typer.echo(f"    [ALERTA] {source} — sem resultados há 3+ execuções")
    else:
        typer.echo("    Todas as fontes OK")

    typer.echo("")


# ─── Validate ────────────────────────────────────────────────────────────────


@app.command()
def validate() -> None:
    """Valida config, secrets e conexões."""
    from vera.config import check_required_secrets, load_config

    typer.echo("Validando configuração...\n")

    # 1. Carrega config
    try:
        config = load_config()
        typer.echo("  [OK] config.yaml carregado")
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"  [ERRO] {e}")
        raise typer.Exit(code=1)

    # 2. Verifica env vars
    errors = check_required_secrets(config)
    if errors:
        for err in errors:
            typer.echo(f"  [ERRO] {err}")
        raise typer.Exit(code=1)
    typer.echo("  [OK] Env vars obrigatórias definidas")

    # 3. Testa backend
    typer.echo(f"\n  Testando backend ({config.backend.type})...")
    try:
        if config.backend.type == "notion":
            from vera.backends.notion import NotionBackend

            backend = NotionBackend(token_env=config.backend.notion.token_env)

            # Tenta buscar databases acessíveis
            dbs = asyncio.run(backend.search_databases())
            typer.echo(f"  [OK] Notion conectado — {len(dbs)} database(s) encontrado(s)")
            for db in dbs[:5]:
                typer.echo(f"       - {db['title']} ({db['id'][:8]}...)")
        else:
            typer.echo(f"  [AVISO] Backend '{config.backend.type}' não tem validação implementada")
    except Exception as e:
        typer.echo(f"  [ERRO] Backend: {e}")
        raise typer.Exit(code=1)

    # 4. Testa LLM
    default_llm = config.llm.default
    typer.echo(f"\n  Testando LLM ({default_llm})...")
    try:
        provider = _create_llm_provider(config, default_llm)
        result = asyncio.run(
            provider.generate(
                system_prompt="Responda em uma palavra.",
                user_prompt="Diga 'ok'.",
                max_tokens=10,
            )
        )
        typer.echo(f"  [OK] LLM respondeu: {result[:50]}")
    except Exception as e:
        typer.echo(f"  [ERRO] LLM: {e}")
        raise typer.Exit(code=1)

    # 5. Testa Telegram (se configurado)
    tg_token = os.environ.get(config.delivery.telegram.bot_token_env, "")
    if tg_token:
        typer.echo("\n  Testando Telegram...")
        try:
            import aiohttp

            async def _test_telegram():
                url = f"https://api.telegram.org/bot{tg_token}/getMe"
                ssl_ctx = False if os.environ.get("VERA_SSL_VERIFY", "1") == "0" else None
                connector = aiohttp.TCPConnector(ssl=ssl_ctx) if ssl_ctx is False else None
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(url) as resp:
                        data = await resp.json()
                        return data

            data = asyncio.run(_test_telegram())
            if data.get("ok"):
                bot_name = data["result"].get("username", "?")
                typer.echo(f"  [OK] Telegram bot: @{bot_name}")
            else:
                typer.echo(f"  [ERRO] Telegram: {data}")
                raise typer.Exit(code=1)
        except Exception as e:
            typer.echo(f"  [ERRO] Telegram: {e}")
            raise typer.Exit(code=1)
    else:
        typer.echo("\n  [SKIP] Telegram não configurado")

    # 6. Verifica domínios
    typer.echo("\n  Domínios configurados:")
    for name, domain_cfg in config.domains.items():
        status = "ativo" if domain_cfg.enabled else "desativado"
        coll = domain_cfg.collection
        collection = coll[:8] + "..." if coll else "sem collection"
        typer.echo(f"    - {name}: {status} ({collection})")

    typer.echo("\nValidação completa!")


def _create_backend(config):
    """Cria instância de StorageBackend a partir do config."""
    if config.backend.type == "notion":
        from vera.backends.notion import NotionBackend

        return NotionBackend(token_env=config.backend.notion.token_env)
    else:
        raise ValueError(f"Backend '{config.backend.type}' não suportado")


def _enviar_telegram(config, mensagem: str) -> None:
    """Envia mensagem no Telegram usando modulo integrations."""
    from vera.integrations.telegram import enviar_telegram

    tg_token = os.environ.get(config.delivery.telegram.bot_token_env, "")
    tg_chat_id = os.environ.get(config.delivery.telegram.chat_id_env, "")

    try:
        asyncio.run(enviar_telegram(mensagem, tg_token, tg_chat_id))
    except Exception as e:
        print(f"   [telegram] Falha ao enviar: {e}")


def _notificar_erro_telegram(config, erro: str) -> None:
    """Notifica erro no Telegram com fallback de 3 niveis."""
    from vera.integrations.telegram import notificar_erro

    tg_token = os.environ.get(config.delivery.telegram.bot_token_env, "")
    tg_chat_id = os.environ.get(config.delivery.telegram.chat_id_env, "")

    try:
        asyncio.run(notificar_erro(erro, tg_token, tg_chat_id))
    except Exception:
        pass


def _create_llm_provider(config, provider_name: str):
    """Cria instância de LLMProvider a partir do config."""
    from vera.config import resolve_env

    provider_cfg = config.llm.providers.get(provider_name)
    if not provider_cfg:
        raise ValueError(f"Provider '{provider_name}' não encontrado no config")

    if provider_name == "claude":
        from vera.llm.claude import ClaudeProvider

        return ClaudeProvider(
            model=provider_cfg.model,
            api_key=resolve_env(provider_cfg.api_key_env) if provider_cfg.api_key_env else None,
            api_key_env=provider_cfg.api_key_env,
        )
    elif provider_name == "ollama":
        from vera.llm.ollama import OllamaProvider

        return OllamaProvider(
            model=provider_cfg.model,
            base_url=provider_cfg.base_url or "http://localhost:11434",
        )
    elif provider_name == "openai":
        raise NotImplementedError("OpenAI provider ainda não implementado. Use Claude ou Ollama.")
    else:
        raise ValueError(f"Provider '{provider_name}' não suportado")


# ─── Bot ─────────────────────────────────────────────────────────────────────


@app.command()
def bot() -> None:
    """Inicia bot Telegram (polling). Responde /status, /next, /help."""
    from vera.config import load_config
    from vera.integrations.telegram_bot import VeraBot

    try:
        config = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Erro ao carregar config: {e}")
        raise typer.Exit(code=1)

    bot_token = os.environ.get(config.delivery.telegram.bot_token_env, "")
    chat_id = os.environ.get(config.delivery.telegram.chat_id_env, "")

    if not bot_token or not chat_id:
        typer.echo("TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID são obrigatórios.")
        raise typer.Exit(code=1)

    typer.echo("Vera Bot iniciando... (Ctrl+C para parar)")
    vera_bot = VeraBot(bot_token, chat_id, config)

    try:
        asyncio.run(vera_bot.start())
    except KeyboardInterrupt:
        typer.echo("\nBot encerrado.")


# ─── Setup ───────────────────────────────────────────────────────────────────


@app.command()
def setup() -> None:
    """Wizard interativo para primeiro setup. Gera config.yaml e .env."""
    from vera.setup.wizard import run_setup_wizard

    run_setup_wizard()


# ─── Doctor ──────────────────────────────────────────────────────────────────


@app.command()
def doctor() -> None:
    """Diagnóstico do sistema: verifica config, secrets e conexões."""
    from vera.doctor import print_results, run_all_checks

    results = asyncio.run(run_all_checks())
    exit_code = print_results(results)
    raise typer.Exit(code=exit_code)
