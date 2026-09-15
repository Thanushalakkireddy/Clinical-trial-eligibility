"""Runtime configuration validation for normal application startup.

This is a real-services application in development and production:

- ``GEMINI_API_KEY`` is required so the Gemini service calls the real API.
- ``DATABASE_URL`` must be a PostgreSQL URL so the app uses SQLAlchemy 2.x
  async + asyncpg + PostgreSQL for persistence and LangGraph checkpointing.

Startup validation is **strict** for normal application runs and is only
skipped in an explicit test environment (``ENVIRONMENT=test``), where tests
configure their own isolated SQLite databases and mocked Gemini services.

None of the helpers here read, log, or render secret values. Error messages
reference environment variable names and expected formats only.
"""

from __future__ import annotations

from typing import List, Optional

from app.config import Settings, settings as global_settings

_POSTGRES_PREFIXES = ("postgresql+asyncpg://", "postgresql://", "postgres://")


class RuntimeConfigError(RuntimeError):
    """Raised when a normal application run lacks required service configuration."""


def strict_validation_enabled(cfg: Settings) -> bool:
    """True for normal runtime environments (validation is enforced).

    Only ``environment == "test"`` opts out; anything else (development,
    production, staging, ...) requires the real external services.
    """
    return (cfg.environment or "").strip().lower() != "test"


def xai_is_configured(cfg: Settings) -> bool:
    """Whether a non-empty xAI API key is configured (boolean only)."""
    return bool((cfg.xai_api_key or "").strip())


def gemini_is_configured(cfg: Settings) -> bool:
    """Whether a non-empty Gemini API key is configured (boolean only)."""
    return bool((cfg.gemini_api_key or "").strip())


def llm_is_configured(cfg: Settings) -> bool:
    """Whether the configured LLM provider has its API key configured."""
    provider = (cfg.llm_provider or "xai").strip().lower()
    if provider == "xai":
        return xai_is_configured(cfg)
    elif provider == "gemini":
        return gemini_is_configured(cfg)
    return xai_is_configured(cfg) or gemini_is_configured(cfg)


def database_is_configured(cfg: Settings) -> bool:
    """Whether a non-empty DATABASE_URL is configured (boolean only)."""
    return bool((cfg.database_url or "").strip())


def _database_is_postgres(cfg: Settings) -> bool:
    url = (cfg.database_url or "").strip()
    return url.startswith(_POSTGRES_PREFIXES)


def validate_runtime_config(cfg: Optional[Settings] = None) -> List[str]:
    """Return the list of configuration problems for a production run.

    This is a pure value check over the given settings: it does not consult
    the environment gate, does not connect to any service, and never includes
    secret values in the returned messages.
    """
    c = cfg or global_settings
    problems: List[str] = []

    provider = (c.llm_provider or "xai").strip().lower()
    if provider == "xai":
        if not xai_is_configured(c):
            problems.append(
                "XAI_API_KEY is not configured. Set XAI_API_KEY=<xAI API key> "
                "in your environment or .env before starting the application."
            )
    elif provider == "gemini":
        if not gemini_is_configured(c):
            problems.append(
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY=<Gemini API key> "
                "in your environment or .env before starting the application."
            )
    else:
        if not llm_is_configured(c):
            problems.append(
                f"LLM API key is not configured for provider '{c.llm_provider}'. "
                "Set XAI_API_KEY or GEMINI_API_KEY in your environment."
            )

    if not database_is_configured(c):
        problems.append(
            "DATABASE_URL is not configured. Set "
            "DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE "
            "to use PostgreSQL persistence (SQLAlchemy async / asyncpg)."
        )
    elif not _database_is_postgres(c):
        problems.append(
            "DATABASE_URL must point to PostgreSQL, e.g. "
            "postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE. "
            "SQLite/other backends are only supported in test mode (ENVIRONMENT=test)."
        )

    return problems


def require_runtime_config(cfg: Optional[Settings] = None) -> None:
    """Fail fast with a clear configuration error in normal runtime mode.

    Raises RuntimeConfigError with all detected problems when the configured
    environment is not the explicit test environment. In test mode the check
    is skipped entirely so tests can supply their own configuration.
    """
    c = cfg or global_settings
    if not strict_validation_enabled(c):
        return
    problems = validate_runtime_config(c)
    if problems:
        raise RuntimeConfigError(
            "Invalid service configuration. Resolve the following before starting the application:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )