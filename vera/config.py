"""Config system — Pydantic models + YAML loader.

Carrega config.yaml + fallback env vars. Erro claro no startup se inválida.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

# ─── Models ──────────────────────────────────────────────────────────────────


class NotionConfig(BaseModel):
    token_env: str = "NOTION_TOKEN"


class BackendConfig(BaseModel):
    type: str = "notion"
    notion: NotionConfig = Field(default_factory=NotionConfig)


class ProviderConfig(BaseModel):
    model: str = ""
    api_key_env: str = ""
    base_url: str = ""


class LLMConfig(BaseModel):
    default: str = "claude"
    advanced: str = "claude"
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class TelegramConfig(BaseModel):
    bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "TELEGRAM_CHAT_ID"


class DeliveryConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class ScheduleTimeConfig(BaseModel):
    day: str = ""
    time: str = ""


class ScheduleConfig(BaseModel):
    briefing: str = "09:00"
    urgency_update: str = "08:00"
    weekly_review: ScheduleTimeConfig = Field(
        default_factory=lambda: ScheduleTimeConfig(day="saturday", time="10:00")
    )
    week_setup: ScheduleTimeConfig = Field(
        default_factory=lambda: ScheduleTimeConfig(day="sunday", time="18:00")
    )


class PersonaConfig(BaseModel):
    preset: str = "executive"
    custom_prompt_file: str | None = None


class DomainFieldsConfig(BaseModel):
    """Campos de um domínio — aceita qualquer campo customizado."""

    model_config = {"extra": "allow"}


class DomainConfig(BaseModel):
    enabled: bool = False
    collection: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)


class GoogleCalendarConfig(BaseModel):
    enabled: bool = False
    credentials_env: str = "GOOGLE_CREDENTIALS"
    oauth_token_env: str = "GOOGLE_OAUTH_TOKEN"
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])


class IntegrationsConfig(BaseModel):
    google_calendar: GoogleCalendarConfig = Field(default_factory=GoogleCalendarConfig)


class ResearchPackConfig(BaseModel):
    """Config de um pack de research."""

    enabled: bool = False
    config_path: str = ""


class ResearchConfig(BaseModel):
    """Config do sistema de Research Packs."""

    enabled: bool = False
    packs: dict[str, ResearchPackConfig] = Field(default_factory=dict)


class DebugConfig(BaseModel):
    dry_run: bool = False
    verbose: bool = False


class VeraConfig(BaseModel):
    """Configuração completa da Vera."""

    name: str = "Vera"
    language: str = "pt-BR"
    timezone: str = "America/Sao_Paulo"

    backend: BackendConfig = Field(default_factory=BackendConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    domains: dict[str, DomainConfig] = Field(default_factory=dict)
    debug: DebugConfig = Field(default_factory=DebugConfig)

    @model_validator(mode="after")
    def validar_tasks_obrigatorio(self) -> "VeraConfig":
        """Tasks é o único domínio obrigatório."""
        if "tasks" not in self.domains:
            self.domains["tasks"] = DomainConfig(enabled=True)
        return self


# ─── Loader ──────────────────────────────────────────────────────────────────


def _find_config_file() -> Path | None:
    """Busca config.yaml em ordem de prioridade."""
    candidates = [
        Path(os.environ.get("VERA_CONFIG", "")),
        Path("config.yaml"),
        Path("config/config.yaml"),
    ]
    for p in candidates:
        if p.name and p.exists():
            return p
    return None


def load_config(path: str | Path | None = None) -> VeraConfig:
    """Carrega configuração de YAML + env vars.

    Args:
        path: caminho para config.yaml. Se None, busca automaticamente.

    Returns:
        VeraConfig validada.

    Raises:
        FileNotFoundError: se nenhum config.yaml encontrado.
        ValueError: se configuração inválida.
    """
    if path is not None:
        config_path = Path(path)
    else:
        config_path = _find_config_file()

    if config_path is None or not config_path.exists():
        raise FileNotFoundError(
            "Arquivo config.yaml não encontrado. "
            "Rode 'python -m vera setup' para criar um, "
            "ou copie config/config.example.yaml para config.yaml."
        )

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return VeraConfig(**raw)


def resolve_env(env_name: str) -> str:
    """Resolve o valor de uma env var. Retorna '' se não definida."""
    return os.environ.get(env_name, "")


def check_required_secrets(config: VeraConfig) -> list[str]:
    """Verifica se env vars obrigatórias estão definidas.

    Retorna lista de erros (vazia = tudo OK).
    """
    errors: list[str] = []

    # Backend
    if config.backend.type == "notion":
        token_env = config.backend.notion.token_env
        if not resolve_env(token_env):
            errors.append(f"Env var '{token_env}' não definida (token Notion)")

    # LLM default
    default_provider = config.llm.default
    if default_provider in config.llm.providers:
        provider = config.llm.providers[default_provider]
        if provider.api_key_env and not resolve_env(provider.api_key_env):
            errors.append(
                f"Env var '{provider.api_key_env}' não definida "
                f"(API key do provider '{default_provider}')"
            )

    return errors
