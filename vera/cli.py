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
) -> None:
    """Gera e envia o briefing diário."""
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
        resultado = run(config, backend, llm, force=force, dry_run=effective_dry_run)

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
        None, help="Nome do pack (news, jobs, financial). Omitir com --list."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Executa sem gravar state."),
    force: bool = typer.Option(False, "--force", "-f", help="Ignorar dedup."),
    list_packs: bool = typer.Option(False, "--list", help="Listar packs disponíveis."),
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

    if not pack:
        typer.echo("Especifique um pack ou use --list. Ex: vera research news")
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


# ─── Setup ───────────────────────────────────────────────────────────────────


@app.command()
def setup() -> None:
    """Wizard interativo para primeiro setup. Gera config.yaml e .env."""
    typer.echo("=" * 50)
    typer.echo("  Vera — Setup Wizard")
    typer.echo("=" * 50)
    typer.echo()

    config_data: dict = {}

    # 1. Nome
    name = typer.prompt("Nome da assistente", default="Vera")
    config_data["name"] = name

    # 2. Idioma
    config_data["language"] = typer.prompt("Idioma", default="pt-BR")

    # 3. Timezone
    default_tz = _detect_timezone()
    config_data["timezone"] = typer.prompt("Timezone", default=default_tz)

    # 4. Backend
    typer.echo("\nOnde você guarda seus dados?")
    typer.echo("  [1] Notion (recomendado)")
    typer.echo("  [2] Outro (experimental)")
    backend_choice = typer.prompt("Escolha", default="1")

    env_vars: dict[str, str] = {}

    if backend_choice == "1":
        config_data["backend"] = {"type": "notion", "notion": {"token_env": "NOTION_TOKEN"}}

        notion_token = typer.prompt(
            "Token da integração Notion (ntnl_...)",
            hide_input=True,
        )
        env_vars["NOTION_TOKEN"] = notion_token

        # Auto-discovery
        typer.echo("\nBuscando databases Notion...")
        discovered = _try_notion_discovery(notion_token)

        if discovered:
            typer.echo(f"  Encontrados {len(discovered)} database(s):")
            for db in discovered:
                typer.echo(f"    - {db['title']} ({db['id'][:8]}...)")
        else:
            typer.echo("  Nenhum database encontrado automaticamente.")
            typer.echo("  Você pode preencher os IDs manualmente no config.yaml depois.")
    else:
        config_data["backend"] = {"type": "custom"}
        typer.echo("  Backend customizado. Configure manualmente no config.yaml.")
        discovered = []

    # 5. LLM
    typer.echo("\nQual LLM usar?")
    typer.echo("  [1] Claude (recomendado)")
    typer.echo("  [2] Ollama (local, gratuito)")
    typer.echo("  [3] OpenAI")
    llm_choice = typer.prompt("Escolha", default="1")

    providers: dict = {}
    default_llm = "claude"

    if llm_choice == "1":
        api_key = typer.prompt("API key Anthropic (sk-ant-...)", hide_input=True)
        env_vars["ANTHROPIC_API_KEY"] = api_key
        providers["claude"] = {
            "model": "claude-sonnet-4-5-20250929",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
        default_llm = "claude"

    elif llm_choice == "2":
        model = typer.prompt("Modelo Ollama", default="llama3.2:3b")
        base_url = typer.prompt("URL do Ollama", default="http://localhost:11434")
        providers["ollama"] = {"model": model, "base_url": base_url}
        default_llm = "ollama"

    elif llm_choice == "3":
        api_key = typer.prompt("API key OpenAI (sk-...)", hide_input=True)
        env_vars["OPENAI_API_KEY"] = api_key
        providers["openai"] = {
            "model": "gpt-4o",
            "api_key_env": "OPENAI_API_KEY",
        }
        default_llm = "openai"

    config_data["llm"] = {
        "default": default_llm,
        "advanced": default_llm,
        "providers": providers,
    }

    # 6. Telegram
    typer.echo("\nConfigurar Telegram para entrega dos briefings?")
    use_telegram = typer.confirm("Configurar Telegram?", default=True)

    if use_telegram:
        typer.echo("  Crie um bot via @BotFather no Telegram e cole o token.")
        bot_token = typer.prompt("Bot token", hide_input=True)
        env_vars["TELEGRAM_BOT_TOKEN"] = bot_token

        typer.echo("  Envie /start para o bot e descubra seu chat_id via @userinfobot.")
        chat_id = typer.prompt("Chat ID")
        env_vars["TELEGRAM_CHAT_ID"] = chat_id

        config_data["delivery"] = {
            "telegram": {
                "bot_token_env": "TELEGRAM_BOT_TOKEN",
                "chat_id_env": "TELEGRAM_CHAT_ID",
            }
        }

    # 7. Persona
    typer.echo("\nEscolha a persona da assistente:")
    typer.echo("  [1] Executiva (direta, irônica, cobra resultados)")
    typer.echo("  [2] Coach (encorajadora, foco em progresso)")
    typer.echo("  [3] Custom (usa workspace/AGENT.md)")
    persona_choice = typer.prompt("Escolha", default="1")

    persona_map = {"1": "executive", "2": "coach", "3": "custom"}
    config_data["persona"] = {"preset": persona_map.get(persona_choice, "executive")}
    if persona_choice == "3":
        config_data["persona"]["custom_prompt_file"] = "workspace/AGENT.md"

    # 8. Domínios
    typer.echo("\nQuais áreas da vida quer gerenciar?")
    typer.echo("  (tasks é obrigatório e já está ativo)")

    domains: dict = {}

    # Tasks — obrigatório
    tasks_domain: dict = {
        "enabled": True,
        "collection": "",
        "fields": {
            "title": "Name",
            "status": "Status",
            "priority": "Prioridade",
            "deadline": "Deadline",
            "category": "Tipo",
            "status_active": ["To Do", "Doing", "Em andamento"],
            "status_done": ["Done", "Concluído"],
        },
    }

    # Auto-fill de discovered databases
    if discovered:
        for db in discovered:
            title_lower = db["title"].lower()
            if "task" in title_lower or "tarefa" in title_lower:
                tasks_domain["collection"] = db["id"]
                typer.echo(f"  Tasks: auto-detectado → {db['title']}")

    if not tasks_domain["collection"]:
        tasks_id = typer.prompt("  ID do database de Tasks (ou Enter para pular)", default="")
        tasks_domain["collection"] = tasks_id

    domains["tasks"] = tasks_domain

    # Domínios opcionais
    optional_domains = {
        "pipeline": ("Pipeline de oportunidades/vagas", "pipeline"),
        "contacts": ("CRM pessoal / Contatos", "contact"),
        "health": ("Saúde e bem-estar", "health"),
        "finances": ("Finanças pessoais", "finance"),
        "learning": ("Aprendizado", "learning"),
    }

    for domain_name, (label, keyword) in optional_domains.items():
        if typer.confirm(f"  Ativar {label}?", default=False):
            collection_id = ""
            if discovered:
                for db in discovered:
                    if keyword in db["title"].lower():
                        collection_id = db["id"]
                        typer.echo(f"    Auto-detectado → {db['title']}")
                        break

            if not collection_id:
                collection_id = typer.prompt(
                    f"    ID do database de {label} (ou Enter para pular)", default=""
                )

            domains[domain_name] = {"enabled": True, "collection": collection_id}
        else:
            domains[domain_name] = {"enabled": False, "collection": ""}

    config_data["domains"] = domains

    # Schedule e debug (defaults)
    config_data["schedule"] = {
        "briefing": "09:00",
        "urgency_update": "08:00",
        "weekly_review": {"day": "saturday", "time": "10:00"},
        "week_setup": {"day": "sunday", "time": "18:00"},
    }
    config_data["debug"] = {"dry_run": False, "verbose": False}

    # Gera arquivos
    typer.echo("\n" + "=" * 50)
    typer.echo("  Gerando arquivos...")
    typer.echo("=" * 50)

    # config.yaml
    config_path = Path("config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    typer.echo(f"\n  [OK] {config_path} criado")

    # .env
    if env_vars:
        env_path = Path(".env")
        with open(env_path, "w", encoding="utf-8") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        typer.echo(f"  [OK] {env_path} criado ({len(env_vars)} variáveis)")

    typer.echo("\nSetup completo! Próximos passos:")
    typer.echo("  1. Revise config.yaml e .env")
    typer.echo("  2. Rode: python -m vera validate")
    typer.echo("  3. Rode: python -m vera briefing --dry-run")


def _detect_timezone() -> str:
    """Tenta detectar timezone do sistema."""
    try:
        import time

        offset = time.timezone if time.daylight == 0 else time.altzone
        hours = -offset // 3600
        # Mapeamento básico de offset para timezone comum
        tz_map = {
            -3: "America/Sao_Paulo",
            -5: "America/New_York",
            -6: "America/Chicago",
            -8: "America/Los_Angeles",
            0: "Europe/London",
            1: "Europe/Berlin",
            9: "Asia/Tokyo",
        }
        return tz_map.get(hours, "America/Sao_Paulo")
    except Exception:
        return "America/Sao_Paulo"


def _try_notion_discovery(token: str) -> list[dict]:
    """Tenta auto-discovery de databases Notion."""
    try:
        from vera.backends.notion import NotionBackend

        backend = NotionBackend(token=token)
        return asyncio.run(backend.search_databases("Vera"))
    except Exception as e:
        logging.getLogger(__name__).debug("Auto-discovery falhou: %s", e)
        return []


# Precisa importar yaml no escopo do setup
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]
