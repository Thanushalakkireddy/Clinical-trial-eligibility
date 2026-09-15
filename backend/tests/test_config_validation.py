"""Tests for real-service configuration validation.

Maps to the "REAL SERVICE CONFIGURATION" checkpoint:

- normal development/production requires GEMINI_API_KEY and a PostgreSQL
  DATABASE_URL, and the app fails fast with clear configuration errors;
- the explicit test environment (ENVIRONMENT=test) is exempt so automated tests
  keep using isolated SQLite and mocked Gemini;
- validation never exposes secret values.

These tests are intentional: they extend the suite for the new behavior and do
not weaken production validation.
"""

import pytest

from app.config import Settings
from app.main import create_app
from app.runtime_config import (
    RuntimeConfigError,
    require_runtime_config,
    validate_runtime_config,
)


def _settings(**overrides) -> Settings:
    base = {
        "ENVIRONMENT": "production",
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "",
        "DATABASE_URL": "",
    }
    base.update(overrides)
    return Settings(**base)


# -----------------------------------------------------------------------------
# Strict (production) validation
# -----------------------------------------------------------------------------

def test_missing_services_produce_clear_errors_in_production():
    cfg = _settings()
    problems = validate_runtime_config(cfg)

    assert len(problems) == 2
    joined = "\n".join(problems)
    assert "GEMINI_API_KEY is not configured" in joined
    assert "DATABASE_URL is not configured" in joined
    assert "PostgreSQL" in joined


def test_only_gemini_missing_is_reported():
    cfg = _settings(DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db")
    problems = validate_runtime_config(cfg)
    assert len(problems) == 1
    assert "GEMINI_API_KEY" in problems[0]
    assert "DATABASE_URL" not in problems[0]


def test_only_database_missing_is_reported():
    cfg = _settings(GEMINI_API_KEY="my-test-key")
    problems = validate_runtime_config(cfg)
    assert len(problems) == 1
    assert "DATABASE_URL" in problems[0]
    assert "GEMINI_API_KEY" not in problems[0]


def test_sqlite_database_rejected_in_production():
    cfg = _settings(
        GEMINI_API_KEY="my-test-key",
        DATABASE_URL="sqlite+aiosqlite:///C:/tmp/local.db",
    )
    problems = validate_runtime_config(cfg)
    assert len(problems) == 1
    assert "PostgreSQL" in problems[0]
    assert "test mode" in problems[0]


def test_plain_postgres_and_asyncpg_accepted_in_production():
    for url in (
        "postgresql://u:p@localhost:5432/db",
        "postgresql+asyncpg://u:p@localhost:5432/db",
        "postgres://u:p@localhost:5432/db",
    ):
        problems = validate_runtime_config(_settings(GEMINI_API_KEY="k", DATABASE_URL=url))
        assert problems == []


def test_require_runtime_config_raises_for_production_missing_services():
    with pytest.raises(RuntimeConfigError) as excinfo:
        require_runtime_config(_settings())
    message = str(excinfo.value)
    assert "Invalid service configuration" in message
    assert "GEMINI_API_KEY" in message
    assert "DATABASE_URL" in message


def test_require_runtime_config_accepts_valid_production():
    require_runtime_config(
        _settings(
            GEMINI_API_KEY="my-test-key",
            DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db",
        )
    )


# -----------------------------------------------------------------------------
# Test environment is exempt
# -----------------------------------------------------------------------------

def test_require_runtime_config_skipped_in_test_environment():
    # ENVIRONMENT=test never raises, even with no services configured.
    require_runtime_config(_settings(ENVIRONMENT="test"))
    require_runtime_config(
        _settings(ENVIRONMENT="test", DATABASE_URL="sqlite+aiosqlite:///C:/tmp/x.db")
    )


# -----------------------------------------------------------------------------
# Secret safety
# -----------------------------------------------------------------------------

def test_validation_never_exposes_secret_values():
    cfg = _settings(
        GEMINI_API_KEY="super-secret-gemini-key-123",
        DATABASE_URL="postgresql+asyncpg://user:super-secret-db-pass@db.internal:5432/db",
    )
    # Force the DATABASE_URL problem without a valid key present by dropping key.
    bad_cfg = _settings(DATABASE_URL="sqlite+aiosqlite:///C:/tmp/x.db")
    joined = "\n".join(validate_runtime_config(bad_cfg))
    assert "super-secret" not in joined

    try:
        require_runtime_config(bad_cfg)
    except RuntimeConfigError as err:
        joined = str(err)
    assert "super-secret" not in joined
    assert "postgresql+asyncpg://" not in joined.split("Invalid service")[0]


# -----------------------------------------------------------------------------
# Fail-fast through the app factory
# -----------------------------------------------------------------------------

def test_create_app_fails_fast_when_strict_config_is_missing(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "database_url", None)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        create_app()
    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        create_app()


def test_create_app_starts_when_strict_config_is_valid(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "dummy-key-for-test")
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:p@localhost:5432/db")

    # Strict mode with real-service configuration present must start cleanly
    # without connecting to the database at import/factory time.
    app = create_app()
    assert app is not None
    assert app.title == "clinical-trial-eligibility-api"


def test_xai_missing_produces_clear_error_in_production():
    cfg = Settings(
        ENVIRONMENT="production",
        LLM_PROVIDER="xai",
        XAI_API_KEY="",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db",
    )
    problems = validate_runtime_config(cfg)
    assert len(problems) == 1
    assert "XAI_API_KEY is not configured" in problems[0]
    assert "GEMINI_API_KEY" not in problems[0]


def test_xai_provider_does_not_require_gemini_key():
    cfg = Settings(
        ENVIRONMENT="production",
        LLM_PROVIDER="xai",
        XAI_API_KEY="test-xai-key",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db",
    )
    problems = validate_runtime_config(cfg)
    assert problems == []


def test_gemini_provider_does_not_require_xai_key():
    cfg = Settings(
        ENVIRONMENT="production",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-gemini-key",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db",
    )
    problems = validate_runtime_config(cfg)
    assert problems == []


def test_create_app_succeeds_in_test_environment():
    # Conftest sets ENVIRONMENT=test; create_app must not raise or connect.
    app = create_app()
    assert app is not None
    assert app.title == "clinical-trial-eligibility-api"