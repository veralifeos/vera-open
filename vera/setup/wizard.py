"""Main setup wizard — InquirerPy with typer.prompt fallback."""

import asyncio
import sys
from pathlib import Path

import typer

try:
    from InquirerPy import inquirer

    HAS_INQUIRER = True
except ImportError:
    HAS_INQUIRER = False

# Preset map: objetivo → preset file path
PRESET_MAP = {
    "jobs": "config/presets/config.jobs.yaml",
    "briefing": "config/presets/config.briefing.yaml",
    "minimal": "config/presets/config.minimal.yaml",
}

# Domains enabled per preset
PRESET_DOMAINS = {
    "jobs": ["tasks", "pipeline", "contacts", "check_semanal"],
    "briefing": ["tasks", "check_semanal"],
    "minimal": ["tasks"],
}


def _prompt_text(message: str, default: str = "", password: bool = False) -> str:
    """Text prompt with InquirerPy or typer fallback."""
    if HAS_INQUIRER:
        return inquirer.text(message=message, default=default).execute()
    return typer.prompt(message, default=default or None, hide_input=password) or default


def _prompt_password(message: str) -> str:
    """Password prompt. Returns empty string if user enters nothing."""
    if HAS_INQUIRER:
        return inquirer.secret(message=message).execute()
    return typer.prompt(message, hide_input=True, default="")


def _prompt_select(message: str, choices: list[dict]) -> str:
    """Select prompt. choices: [{"name": "display", "value": "key"}, ...]"""
    if HAS_INQUIRER:
        return inquirer.select(message=message, choices=choices).execute()
    # Fallback: numbered list
    typer.echo(f"\n{message}")
    for i, c in enumerate(choices, 1):
        typer.echo(f"  [{i}] {c['name']}")
    while True:
        raw = typer.prompt("Escolha", default="1")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]["value"]
        except ValueError:
            pass
        typer.echo("  Opção inválida, tente novamente.")


def _prompt_confirm(message: str, default: bool = True) -> bool:
    """Confirm prompt."""
    if HAS_INQUIRER:
        return inquirer.confirm(message=message, default=default).execute()
    return typer.confirm(message, default=default)


def _detect_timezone() -> str:
    """Detect system timezone. Uses tzlocal if available, falls back to offset mapping."""
    try:
        from tzlocal import get_localzone

        tz = get_localzone()
        return str(tz)
    except ImportError:
        pass

    try:
        import time

        offset = time.timezone if time.daylight == 0 else time.altzone
        hours = -offset // 3600
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


def _print_status(ok: bool, message: str) -> None:
    """Print a status line with color."""
    if ok:
        typer.echo(f"  ✓ {message}")
    else:
        typer.echo(f"  ✗ {message}")


def run_setup_wizard() -> None:
    """Main wizard entry point."""
    typer.echo("=" * 50)
    typer.echo("  Vera — Setup Wizard")
    typer.echo("=" * 50)
    typer.echo()

    answers: dict = {}
    env_vars: dict[str, str] = {}

    # ── 1. Nome ──────────────────────────────────────────────────────────────
    answers["name"] = _prompt_text("Nome da assistente", default="Vera")

    # ── 2. Timezone ──────────────────────────────────────────────────────────
    default_tz = _detect_timezone()
    typer.echo(f"  Timezone detectada: {default_tz}")
    if _prompt_confirm(f"Usar {default_tz}?", default=True):
        answers["timezone"] = default_tz
    else:
        answers["timezone"] = _prompt_text("Timezone (IANA)", default=default_tz)

    answers["language"] = "pt-BR"

    # ── 3. Objetivo (preset) ─────────────────────────────────────────────────
    preset_key = _prompt_select(
        "Qual o seu objetivo principal?",
        [
            {"name": "Recolocação profissional (Tasks + Pipeline + Jobs)", "value": "jobs"},
            {"name": "Briefing pessoal (Tasks + Check Semanal + News)", "value": "briefing"},
            {"name": "Teste rápido (só Tasks)", "value": "minimal"},
        ],
    )
    preset_path = PRESET_MAP[preset_key]
    enabled_domains = PRESET_DOMAINS[preset_key]

    # ── 4. Notion ────────────────────────────────────────────────────────────
    typer.echo("\n── Notion ──")
    typer.echo("  Crie uma integração em: https://www.notion.so/my-integrations")

    notion_token = ""
    databases: list[dict] = []
    db_ids: dict[str, str] = {}
    max_attempts = 3

    for attempt in range(max_attempts):
        notion_token = _prompt_password("Token da integração (ntnl_...)")
        if not notion_token:
            typer.echo("  Token vazio, pulando Notion.")
            break

        typer.echo("  Validando...")
        from vera.setup.validators import validate_notion_token

        ok, msg, databases = asyncio.run(validate_notion_token(notion_token))
        _print_status(ok, msg)

        if ok:
            env_vars["NOTION_TOKEN"] = notion_token
            break
        elif attempt < max_attempts - 1:
            typer.echo("  Tente novamente.")
        else:
            typer.echo("  Máximo de tentativas. Configure manualmente no .env depois.")

    if notion_token and env_vars.get("NOTION_TOKEN"):
        answers["backend"] = {"type": "notion", "notion": {"token_env": "NOTION_TOKEN"}}

        # Offer DB creation or discovery
        db_strategy = _prompt_select(
            "Como configurar os databases?",
            [
                {"name": "Criar databases automaticamente", "value": "create"},
                {"name": "Já tenho databases (auto-detectar)", "value": "discover"},
                {"name": "Vou configurar manualmente depois", "value": "manual"},
            ],
        )

        if db_strategy == "create":
            typer.echo("\n  Criando databases no Notion...")
            # Find parent page
            from vera.setup.notion_setup import find_accessible_pages, provision_workspace

            pages = asyncio.run(find_accessible_pages(notion_token))
            if pages:
                if len(pages) == 1:
                    parent_id = pages[0]["id"]
                    typer.echo(f"  Usando página: {pages[0]['title']}")
                else:
                    parent_choices = [
                        {"name": p["title"], "value": p["id"]} for p in pages[:10]
                    ]
                    parent_id = _prompt_select(
                        "Escolha a página pai para os databases:", parent_choices
                    )

                try:
                    db_ids = asyncio.run(
                        provision_workspace(notion_token, parent_id, enabled_domains)
                    )
                    for domain, db_id in db_ids.items():
                        _print_status(True, f"{domain}: {db_id[:12]}...")
                except Exception as e:
                    typer.echo(f"  Erro ao criar databases: {e}")
                    typer.echo("  Configure manualmente depois.")
            else:
                typer.echo("  Nenhuma página acessível. Compartilhe uma página com a integração.")

        elif db_strategy == "discover":
            if databases:
                typer.echo(f"\n  {len(databases)} database(s) encontrado(s):")
                for db in databases:
                    typer.echo(f"    - {db['title']} ({db['id'][:8]}...)")
                # Auto-match by domain keywords
                for domain in enabled_domains:
                    keywords = {
                        "tasks": ["task", "tarefa"],
                        "pipeline": ["pipeline", "vaga"],
                        "contacts": ["contact", "contato"],
                        "check_semanal": ["check", "semanal"],
                    }.get(domain, [domain])
                    for db in databases:
                        title_lower = db["title"].lower()
                        if any(kw in title_lower for kw in keywords):
                            db_ids[domain] = db["id"]
                            typer.echo(f"  {domain} → {db['title']}")
                            break
            else:
                typer.echo("  Nenhum database encontrado. Configure manualmente.")
    else:
        answers["backend"] = {"type": "notion", "notion": {"token_env": "NOTION_TOKEN"}}

    # Build domain configs
    domains_config: dict = {}
    for domain in enabled_domains:
        domain_cfg: dict = {"enabled": True, "collection": db_ids.get(domain, "")}
        # Add default field mappings
        if domain == "tasks":
            domain_cfg["fields"] = {
                "title": "Name",
                "status": "Status",
                "priority": "Prioridade",
                "deadline": "Deadline",
                "category": "Tipo",
                "status_active": ["To Do", "Doing"],
                "status_done": ["Done"],
            }
        elif domain == "pipeline":
            domain_cfg["fields"] = {
                "title": "Empresa",
                "stage": "Estágio",
                "priority": "Prioridade",
                "next_action": "Próximo Passo",
                "last_contact": "Data Último Contato",
            }
        elif domain == "contacts":
            domain_cfg["fields"] = {
                "name": "Nome",
                "status": "Status",
                "type": "Tipo",
                "last_interaction": "Último Contato",
            }
        elif domain == "check_semanal":
            domain_cfg["fields"] = {
                "semana": "Semana",
                "energia": "Energia",
                "vida_pratica": "Vida Prática",
                "carreira": "Carreira",
                "sanidade": "Sanidade",
                "highlight": "Highlight",
            }
        domains_config[domain] = domain_cfg
    answers["domains"] = domains_config

    # ── 5. Telegram ──────────────────────────────────────────────────────────
    typer.echo("\n── Telegram ──")
    if _prompt_confirm("Configurar Telegram para entrega dos briefings?", default=True):
        typer.echo("  Crie um bot via @BotFather e cole o token.")

        tg_token = ""
        for attempt in range(max_attempts):
            tg_token = _prompt_password("Bot token")
            if not tg_token:
                break

            typer.echo("  Validando...")
            from vera.setup.validators import validate_telegram_token

            ok, msg, username = asyncio.run(validate_telegram_token(tg_token))
            _print_status(ok, msg)

            if ok:
                env_vars["TELEGRAM_BOT_TOKEN"] = tg_token
                break
            elif attempt < max_attempts - 1:
                typer.echo("  Tente novamente.")

        if tg_token and env_vars.get("TELEGRAM_BOT_TOKEN"):
            # Try to detect chat_id
            typer.echo(f"\n  Mande /start para @{username} no Telegram.")
            if _prompt_confirm("Aguardar detecção automática do chat_id?", default=True):
                typer.echo("  Aguardando mensagem (30s)...")
                from vera.setup.validators import detect_telegram_chat_id

                ok, msg, chat_id = asyncio.run(detect_telegram_chat_id(tg_token))
                _print_status(ok, msg)
                if ok:
                    env_vars["TELEGRAM_CHAT_ID"] = chat_id
                else:
                    chat_id = _prompt_text("Chat ID (descubra via @userinfobot)")
                    if chat_id:
                        env_vars["TELEGRAM_CHAT_ID"] = chat_id
            else:
                chat_id = _prompt_text("Chat ID (descubra via @userinfobot)")
                if chat_id:
                    env_vars["TELEGRAM_CHAT_ID"] = chat_id

            answers["delivery"] = {
                "telegram": {
                    "bot_token_env": "TELEGRAM_BOT_TOKEN",
                    "chat_id_env": "TELEGRAM_CHAT_ID",
                }
            }

    # ── 6. LLM ───────────────────────────────────────────────────────────────
    typer.echo("\n── LLM ──")
    llm_choice = _prompt_select(
        "Qual LLM usar?",
        [
            {"name": "Claude (recomendado)", "value": "claude"},
            {"name": "Ollama (local, gratuito)", "value": "ollama"},
        ],
    )

    providers: dict = {}
    if llm_choice == "claude":
        for attempt in range(max_attempts):
            api_key = _prompt_password("API key Anthropic (sk-ant-...)")
            if not api_key:
                break

            typer.echo("  Validando...")
            from vera.setup.validators import validate_claude_api_key

            ok, msg = asyncio.run(validate_claude_api_key(api_key))
            _print_status(ok, msg)

            if ok:
                env_vars["ANTHROPIC_API_KEY"] = api_key
                break
            elif attempt < max_attempts - 1:
                typer.echo("  Tente novamente.")

        providers["claude"] = {
            "model": "claude-sonnet-4-5-20250929",
            "api_key_env": "ANTHROPIC_API_KEY",
        }

    elif llm_choice == "ollama":
        url = _prompt_text("URL do Ollama", default="http://localhost:11434")
        typer.echo("  Testando conexão...")
        from vera.setup.validators import validate_ollama_connection

        ok, msg = asyncio.run(validate_ollama_connection(url))
        _print_status(ok, msg)

        model = _prompt_text("Modelo Ollama", default="llama3.2:3b")
        providers["ollama"] = {"model": model, "base_url": url}

    answers["llm"] = {
        "default": llm_choice,
        "advanced": llm_choice,
        "providers": providers,
    }

    # ── 7. Persona ───────────────────────────────────────────────────────────
    persona = _prompt_select(
        "Persona da assistente:",
        [
            {"name": "Executiva (direta, irônica, cobra resultados)", "value": "executive"},
            {"name": "Coach (encorajadora, foco em progresso)", "value": "coach"},
            {"name": "Custom (usa workspace/AGENT.md)", "value": "custom"},
        ],
    )
    answers["persona"] = {"preset": persona}
    if persona == "custom":
        answers["persona"]["custom_prompt_file"] = "workspace/AGENT.md"

    # ── 8. Generate config files ─────────────────────────────────────────────
    typer.echo("\n" + "=" * 50)
    typer.echo("  Gerando arquivos...")
    typer.echo("=" * 50)

    from vera.setup.config_writer import generate_config_yaml, write_config_file, write_env_file

    config_content = generate_config_yaml(answers, preset_path=preset_path)
    config_path = write_config_file(config_content, Path("config.yaml"))
    typer.echo(f"\n  ✓ {config_path} criado")

    if env_vars:
        env_path = write_env_file(env_vars, Path(".env"))
        typer.echo(f"  ✓ {env_path} criado ({len(env_vars)} variáveis)")

    # ── 9. Auto-run doctor ───────────────────────────────────────────────────
    typer.echo("\n── Diagnóstico ──")
    try:
        from vera.doctor import print_results, run_all_checks

        results = asyncio.run(run_all_checks())
        print_results(results)
    except Exception as e:
        typer.echo(f"  Doctor falhou: {e}")
        typer.echo("  Rode manualmente: python -m vera doctor")

    # ── Done ─────────────────────────────────────────────────────────────────
    typer.echo("\nSetup completo! Próximos passos:")
    typer.echo("  1. Revise config.yaml e .env")
    typer.echo("  2. Rode: python -m vera doctor")
    typer.echo("  3. Rode: python -m vera briefing --dry-run")
