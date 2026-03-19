"""Config file generation — produces config.yaml and .env from wizard answers."""

from pathlib import Path

import yaml


def generate_config_yaml(answers: dict, preset_path: str | None = None) -> str:
    """Generate config.yaml content from wizard answers, optionally overlaying a preset."""
    base: dict = {}

    # Load preset as base if provided
    if preset_path:
        preset = Path(preset_path)
        if preset.exists():
            with open(preset, encoding="utf-8") as f:
                base = yaml.safe_load(f) or {}

    # Overlay wizard answers
    base["name"] = answers.get("name", "Vera")
    base["language"] = answers.get("language", "pt-BR")
    base["timezone"] = answers.get("timezone", "America/Sao_Paulo")

    # Backend
    if answers.get("backend"):
        base["backend"] = answers["backend"]

    # LLM
    if answers.get("llm"):
        base["llm"] = answers["llm"]

    # Delivery (Telegram)
    if answers.get("delivery"):
        base["delivery"] = answers["delivery"]

    # Persona
    if answers.get("persona"):
        base["persona"] = answers["persona"]

    # Domains — merge with preset defaults
    if answers.get("domains"):
        base_domains = base.get("domains", {})
        base_domains.update(answers["domains"])
        base["domains"] = base_domains

    # Schedule — use preset or defaults
    if "schedule" not in base:
        base["schedule"] = {
            "briefing": "09:00",
            "urgency_update": "08:00",
            "weekly_review": {"day": "saturday", "time": "10:00"},
            "week_setup": {"day": "sunday", "time": "18:00"},
        }

    # Research — keep from preset if present
    # (wizard doesn't configure research packs yet)

    # Debug defaults
    if "debug" not in base:
        base["debug"] = {"dry_run": False, "verbose": False}

    return yaml.dump(base, default_flow_style=False, allow_unicode=True, sort_keys=False)


def write_config_file(content: str, path: Path) -> Path:
    """Write config.yaml to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_env_file(env_vars: dict, path: Path) -> Path:
    """Write .env file with key=value pairs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in env_vars.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
