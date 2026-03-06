"""Vera CLI — interface Typer com subcommands."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import typer

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
    # Implementação na Sessão 2
    typer.echo("Briefing será implementado na Sessão 2.")
    typer.echo(f"  force={force}, dry_run={dry_run}")


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
                async with aiohttp.ClientSession() as session:
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
        collection = domain_cfg.collection[:8] + "..." if domain_cfg.collection else "sem collection"
        typer.echo(f"    - {name}: {status} ({collection})")

    typer.echo("\nValidação completa!")


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
    tasks_domain: dict = {"enabled": True, "collection": "", "fields": {
        "title": "Name",
        "status": "Status",
        "priority": "Prioridade",
        "deadline": "Deadline",
        "category": "Tipo",
        "status_active": ["To Do", "Doing", "Em andamento"],
        "status_done": ["Done", "Concluído"],
    }}

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
