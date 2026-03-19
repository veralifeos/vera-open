"""vera doctor — health checks with Rich table output."""

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import typer


class CheckStatus(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    fix_hint: str | None = None


async def check_python_version() -> CheckResult:
    """Check Python >= 3.11."""
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return CheckResult("Python", CheckStatus.OK, f"Python {version_str}")
    return CheckResult(
        "Python",
        CheckStatus.FAIL,
        f"Python {version_str} (precisa >= 3.11)",
        fix_hint="Instale Python 3.11+ em python.org",
    )


async def check_env_file() -> CheckResult:
    """Check .env exists and has required vars."""
    for path in [Path(".env"), Path("config/.env")]:
        if path.exists():
            content = path.read_text(encoding="utf-8-sig")
            vars_found = [
                line.split("=")[0].strip()
                for line in content.splitlines()
                if "=" in line and not line.strip().startswith("#")
            ]
            has_notion = "NOTION_TOKEN" in vars_found
            has_llm = "ANTHROPIC_API_KEY" in vars_found or any(
                "OLLAMA" in v for v in vars_found
            )
            if has_notion and has_llm:
                return CheckResult(
                    ".env", CheckStatus.OK, f"{len(vars_found)} variáveis em {path}"
                )
            missing = []
            if not has_notion:
                missing.append("NOTION_TOKEN")
            if not has_llm:
                missing.append("ANTHROPIC_API_KEY ou Ollama")
            return CheckResult(
                ".env",
                CheckStatus.WARN,
                f"Faltando: {', '.join(missing)}",
                fix_hint="Rode: python -m vera setup",
            )
    return CheckResult(
        ".env",
        CheckStatus.FAIL,
        "Arquivo .env não encontrado",
        fix_hint="Rode: python -m vera setup",
    )


async def check_config_yaml() -> CheckResult:
    """Check config.yaml exists and parses correctly."""
    try:
        from vera.config import load_config

        config = load_config()
        domains_active = sum(1 for d in config.domains.values() if d.enabled)
        return CheckResult(
            "config.yaml",
            CheckStatus.OK,
            f"Válido ({domains_active} domínio(s) ativo(s))",
        )
    except FileNotFoundError:
        return CheckResult(
            "config.yaml",
            CheckStatus.FAIL,
            "Arquivo não encontrado",
            fix_hint="Rode: python -m vera setup",
        )
    except Exception as e:
        return CheckResult(
            "config.yaml",
            CheckStatus.FAIL,
            f"Erro: {e}",
            fix_hint="Verifique a sintaxe YAML",
        )


async def check_notion_token() -> CheckResult:
    """Check Notion token works."""
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        return CheckResult(
            "Notion Token",
            CheckStatus.SKIP,
            "NOTION_TOKEN não definido",
        )

    from vera.setup.validators import validate_notion_token

    ok, msg, dbs = await validate_notion_token(token)
    if ok:
        return CheckResult("Notion Token", CheckStatus.OK, msg)
    return CheckResult(
        "Notion Token",
        CheckStatus.FAIL,
        msg,
        fix_hint="Verifique em notion.so/my-integrations",
    )


async def check_notion_databases() -> CheckResult:
    """Check each domain's database ID is accessible."""
    try:
        from vera.config import load_config

        config = load_config()
    except Exception:
        return CheckResult("Databases", CheckStatus.SKIP, "Config não carregado")

    token = os.environ.get(config.backend.notion.token_env, "")
    if not token:
        return CheckResult("Databases", CheckStatus.SKIP, "Token não disponível")

    import httpx

    from vera.setup.validators import NOTION_API_VERSION, NOTION_BASE_URL, _ssl_verify

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_API_VERSION,
    }

    ok_count = 0
    fail_count = 0
    checked = 0

    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=10) as client:
        for name, domain_cfg in config.domains.items():
            if not domain_cfg.enabled or not domain_cfg.collection:
                continue
            checked += 1
            try:
                resp = await client.post(
                    f"{NOTION_BASE_URL}/databases/{domain_cfg.collection}/query",
                    headers=headers,
                    json={"page_size": 1},
                )
                if resp.status_code == 200:
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception:
                fail_count += 1

    if checked == 0:
        return CheckResult("Databases", CheckStatus.SKIP, "Nenhum domínio com collection")
    if fail_count == 0:
        return CheckResult("Databases", CheckStatus.OK, f"{ok_count}/{checked} acessíveis")
    return CheckResult(
        "Databases",
        CheckStatus.FAIL,
        f"{fail_count}/{checked} inacessíveis",
        fix_hint="Compartilhe os databases com a integração no Notion",
    )


async def check_telegram_bot() -> CheckResult:
    """Check Telegram bot token works."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return CheckResult("Telegram Bot", CheckStatus.SKIP, "Não configurado")

    from vera.setup.validators import validate_telegram_token

    ok, msg, _ = await validate_telegram_token(token)
    if ok:
        return CheckResult("Telegram Bot", CheckStatus.OK, msg)
    return CheckResult(
        "Telegram Bot",
        CheckStatus.FAIL,
        msg,
        fix_hint="Crie um bot via @BotFather",
    )


async def check_telegram_chat_id() -> CheckResult:
    """Check Telegram chat_id is set."""
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return CheckResult("Telegram Chat ID", CheckStatus.SKIP, "Bot não configurado")
        return CheckResult(
            "Telegram Chat ID",
            CheckStatus.WARN,
            "TELEGRAM_CHAT_ID não definido",
            fix_hint="Mande /start pro bot e rode: python -m vera setup",
        )
    return CheckResult("Telegram Chat ID", CheckStatus.OK, f"Chat ID: {chat_id}")


async def check_llm() -> CheckResult:
    """Check LLM provider responds."""
    try:
        from vera.config import load_config

        config = load_config()
    except Exception:
        return CheckResult("LLM", CheckStatus.SKIP, "Config não carregado")

    default_llm = config.llm.default
    provider_cfg = config.llm.providers.get(default_llm)
    if not provider_cfg:
        return CheckResult(
            "LLM",
            CheckStatus.FAIL,
            f"Provider '{default_llm}' não configurado",
        )

    if default_llm == "claude":
        key = os.environ.get(provider_cfg.api_key_env, "")
        if not key:
            return CheckResult(
                "LLM",
                CheckStatus.FAIL,
                f"{provider_cfg.api_key_env} não definido",
            )
        from vera.setup.validators import validate_claude_api_key

        ok, msg = await validate_claude_api_key(key)
        status = CheckStatus.OK if ok else CheckStatus.FAIL
        return CheckResult("LLM (Claude)", status, msg)

    elif default_llm == "ollama":
        url = provider_cfg.base_url or "http://localhost:11434"
        from vera.setup.validators import validate_ollama_connection

        ok, msg = await validate_ollama_connection(url)
        status = CheckStatus.OK if ok else CheckStatus.FAIL
        return CheckResult("LLM (Ollama)", status, msg)

    return CheckResult("LLM", CheckStatus.WARN, f"Provider '{default_llm}' sem validação")


async def check_state_writable() -> CheckResult:
    """Check state/ directory is writable."""
    state_dir = Path("state")
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        test_file = state_dir / ".doctor_test"
        test_file.write_text("ok")
        test_file.unlink()
        return CheckResult("state/", CheckStatus.OK, "Diretório gravável")
    except Exception as e:
        return CheckResult(
            "state/",
            CheckStatus.FAIL,
            f"Não gravável: {e}",
            fix_hint="Verifique permissões do diretório state/",
        )


async def check_user_md() -> CheckResult:
    """Check workspace/USER.md exists."""
    if Path("workspace/USER.md").exists():
        return CheckResult("USER.md", CheckStatus.OK, "workspace/USER.md encontrado")
    return CheckResult(
        "USER.md",
        CheckStatus.WARN,
        "workspace/USER.md não encontrado",
        fix_hint="Copie workspace/USER.example.md → workspace/USER.md e personalize",
    )


# ─── Orchestration ───────────────────────────────────────────────────────────

ALL_CHECKS = [
    check_python_version,
    check_env_file,
    check_config_yaml,
    check_notion_token,
    check_notion_databases,
    check_telegram_bot,
    check_telegram_chat_id,
    check_llm,
    check_state_writable,
    check_user_md,
]


async def run_all_checks() -> list[CheckResult]:
    """Run all health checks sequentially (some depend on config)."""
    results = []
    for check_fn in ALL_CHECKS:
        try:
            result = await check_fn()
        except Exception as e:
            result = CheckResult(check_fn.__name__, CheckStatus.FAIL, f"Erro: {e}")
        results.append(result)
    return results


def print_results(results: list[CheckResult]) -> int:
    """Print results as a formatted table. Returns exit code (0 = no failures)."""
    STATUS_SYMBOLS = {
        CheckStatus.OK: "✓",
        CheckStatus.WARN: "⚠",
        CheckStatus.FAIL: "✗",
        CheckStatus.SKIP: "○",
    }

    typer.echo("\n  Vera — Diagnóstico")
    typer.echo("  " + "─" * 48)

    for r in results:
        symbol = STATUS_SYMBOLS[r.status]
        line = f"  {symbol}  {r.name:<20s} {r.message}"
        typer.echo(line)
        if r.fix_hint and r.status in (CheckStatus.FAIL, CheckStatus.WARN):
            typer.echo(f"      → {r.fix_hint}")

    typer.echo("  " + "─" * 48)

    fails = sum(1 for r in results if r.status == CheckStatus.FAIL)
    warns = sum(1 for r in results if r.status == CheckStatus.WARN)
    oks = sum(1 for r in results if r.status == CheckStatus.OK)

    if fails:
        typer.echo(f"  {fails} erro(s), {warns} aviso(s), {oks} ok")
    elif warns:
        typer.echo(f"  Tudo funcional ({warns} aviso(s))")
    else:
        typer.echo(f"  Tudo OK! ({oks} checks)")

    return 1 if fails else 0
