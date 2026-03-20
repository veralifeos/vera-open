"""vera packs — gestão de Research Packs."""

import shutil
from pathlib import Path

import typer
import yaml

app = typer.Typer(
    name="packs",
    help="Gerencia Research Packs (listar, instalar, habilitar, desabilitar).",
    no_args_is_help=True,
)

PACKS_CONFIG_DIR = Path("config/packs")
PACKS_SOURCE_DIR = Path("vera/research/packs")
CONFIG_YAML = Path("config.yaml")


def _load_config_yaml() -> dict:
    if not CONFIG_YAML.exists():
        # Tenta path alternativo
        alt = Path("config/config.yaml")
        if alt.exists():
            with open(alt, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}, alt
        return {}, CONFIG_YAML
    with open(CONFIG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}, CONFIG_YAML


def _save_config_yaml(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _get_available_packs() -> list[str]:
    """Lista todos os packs com base nos diretórios em vera/research/packs/."""
    if not PACKS_SOURCE_DIR.exists():
        return []
    return sorted(
        d.name for d in PACKS_SOURCE_DIR.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )


def _get_installed_packs() -> list[str]:
    """Packs com config YAML ativo (não-example) em config/packs/."""
    if not PACKS_CONFIG_DIR.exists():
        return []
    return sorted(
        p.stem for p in PACKS_CONFIG_DIR.glob("*.yaml")
        if not p.stem.endswith(".example") and "example" not in p.stem
    )


def _get_enabled_packs(config: dict) -> dict:
    """Retorna dict {pack_name: enabled} da seção research.packs do config."""
    return {
        name: cfg.get("enabled", False)
        for name, cfg in config.get("research", {}).get("packs", {}).items()
    }


# ─── list ─────────────────────────────────────────────────────────────────────


@app.command("list")
def list_packs() -> None:
    """Lista todos os packs disponíveis com seu status atual."""
    from vera.research.registry import registry

    registry.discover()

    available = _get_available_packs()
    installed = set(_get_installed_packs())
    config, _ = _load_config_yaml()
    enabled = _get_enabled_packs(config)
    registered = set(registry.list_available())

    if not available:
        typer.echo("Nenhum pack encontrado em vera/research/packs/")
        return

    typer.echo()
    typer.echo("  Research Packs disponíveis:")
    typer.echo("  " + "─" * 52)
    typer.echo(f"  {'PACK':<16} {'CONFIG':<12} {'ATIVO':<8} {'DESCRIÇÃO'}")
    typer.echo("  " + "─" * 52)

    for name in available:
        pack_cls = registry.get(name)
        desc = getattr(pack_cls, "description", "—") if pack_cls else "—"
        if len(desc) > 30:
            desc = desc[:28] + "…"

        config_status = "✓ instalado" if name in installed else "× exemplo"
        enabled_status = "✓ sim" if enabled.get(name) else "× não"

        typer.echo(f"  {name:<16} {config_status:<12} {enabled_status:<8} {desc}")

    typer.echo()
    typer.echo(f"  Total: {len(available)} pack(s)  |  "
               f"Instalados: {len(installed)}  |  "
               f"Ativos: {sum(1 for v in enabled.values() if v)}")
    typer.echo()
    typer.echo("  Use 'vera packs install <nome>' para instalar um pack.")
    typer.echo()


# ─── install ──────────────────────────────────────────────────────────────────


@app.command()
def install(
    name: str = typer.Argument(..., help="Nome do pack (ex: news, jobs, financial)"),
    enable: bool = typer.Option(True, "--enable/--no-enable", help="Habilitar após instalar."),
    force: bool = typer.Option(False, "--force", "-f", help="Sobrescrever config existente."),
) -> None:
    """Instala um pack: copia o exemplo de config e habilita no config.yaml."""
    available = _get_available_packs()
    if name not in available:
        typer.echo(f"Pack '{name}' não encontrado. Disponíveis: {available}")
        raise typer.Exit(code=1)

    PACKS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    target = PACKS_CONFIG_DIR / f"{name}.yaml"
    example = PACKS_CONFIG_DIR / f"{name}.example.yaml"

    # Verifica se já está instalado
    if target.exists() and not force:
        typer.echo(f"Pack '{name}' já tem config em {target}")
        typer.echo("Use --force para sobrescrever.")
        # Apenas habilita se pedido
        if enable:
            _set_pack_enabled(name, True)
            typer.echo(f"Pack '{name}' habilitado no config.yaml.")
        raise typer.Exit()

    # Copia example → active
    if example.exists():
        shutil.copy2(example, target)
        typer.echo(f"  ✓ Config copiado: {example} → {target}")
    else:
        # Cria config mínimo
        minimal = {"enabled": True, "topics": [], "sources": [], "scoring": {"relevance_threshold": 0.5}}
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(minimal, f, allow_unicode=True, default_flow_style=False)
        typer.echo(f"  ✓ Config mínimo criado em {target}")
        typer.echo(f"  ⚠ Edite {target} para configurar fontes e tópicos.")

    # Habilita no config.yaml
    if enable:
        _set_pack_enabled(name, True, config_path_str=str(target))
        typer.echo(f"  ✓ Pack '{name}' habilitado no config.yaml")

    typer.echo()
    typer.echo(f"Pack '{name}' instalado com sucesso.")
    typer.echo(f"Edite {target} para personalizar tópicos e fontes.")
    typer.echo(f"Rode 'vera research {name} --dry-run' para testar.")


# ─── enable ───────────────────────────────────────────────────────────────────


@app.command()
def enable(
    name: str = typer.Argument(..., help="Nome do pack"),
) -> None:
    """Habilita um pack instalado no config.yaml."""
    installed = _get_installed_packs()
    if name not in installed:
        typer.echo(f"Pack '{name}' não está instalado. Rode 'vera packs install {name}' primeiro.")
        raise typer.Exit(code=1)

    _set_pack_enabled(name, True)
    typer.echo(f"Pack '{name}' habilitado.")


# ─── disable ──────────────────────────────────────────────────────────────────


@app.command()
def disable(
    name: str = typer.Argument(..., help="Nome do pack"),
) -> None:
    """Desabilita um pack (sem remover o config)."""
    _set_pack_enabled(name, False)
    typer.echo(f"Pack '{name}' desabilitado. Config preservado em config/packs/{name}.yaml")


# ─── info ─────────────────────────────────────────────────────────────────────


@app.command()
def info(
    name: str = typer.Argument(..., help="Nome do pack"),
) -> None:
    """Mostra detalhes de um pack: descrição, config atual, status."""
    from vera.research.registry import registry

    registry.discover()

    available = _get_available_packs()
    if name not in available:
        typer.echo(f"Pack '{name}' não encontrado. Disponíveis: {available}")
        raise typer.Exit(code=1)

    pack_cls = registry.get(name)
    config_main, _ = _load_config_yaml()
    enabled_packs = _get_enabled_packs(config_main)
    installed = name in _get_installed_packs()

    typer.echo()
    typer.echo(f"  Pack: {name}")
    typer.echo(f"  Descrição: {getattr(pack_cls, 'description', '—') if pack_cls else '—'}")
    typer.echo(f"  Registrado: {'sim' if pack_cls else 'não'}")
    typer.echo(f"  Config instalado: {'sim' if installed else 'não'}")
    typer.echo(f"  Habilitado: {'sim' if enabled_packs.get(name) else 'não'}")

    # Mostra config atual se existir
    config_path = PACKS_CONFIG_DIR / f"{name}.yaml"
    example_path = PACKS_CONFIG_DIR / f"{name}.example.yaml"

    if config_path.exists():
        typer.echo(f"\n  Config ({config_path}):")
        with open(config_path, encoding="utf-8") as f:
            for line in f.readlines()[:30]:
                typer.echo(f"    {line}", nl=False)
    elif example_path.exists():
        typer.echo(f"\n  Exemplo disponível ({example_path}) — rode 'vera packs install {name}'")

    typer.echo()


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _set_pack_enabled(name: str, enabled: bool, config_path_str: str = "") -> None:
    """Atualiza enabled: true/false no config.yaml para o pack."""
    config, config_path = _load_config_yaml()

    if "research" not in config:
        config["research"] = {"enabled": True, "packs": {}}
    if "packs" not in config["research"]:
        config["research"]["packs"] = {}
    if name not in config["research"]["packs"]:
        config["research"]["packs"][name] = {}

    # Determina path relativo do config do pack
    if not config_path_str:
        config_path_str = str(PACKS_CONFIG_DIR / f"{name}.yaml")

    config["research"]["packs"][name]["enabled"] = enabled
    config["research"]["packs"][name]["config_path"] = config_path_str

    # Habilita research global se habilitando um pack
    if enabled:
        config["research"]["enabled"] = True

    _save_config_yaml(config, config_path)
