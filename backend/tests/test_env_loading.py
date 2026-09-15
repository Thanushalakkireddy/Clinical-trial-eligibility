"""Tests for reliable backend/.env discovery and secret safety.

Maps to the "ENV FILE DISCOVERY" checkpoint:

- ``backend/.env`` is resolved by an absolute path anchored to the backend
  package location, so it loads whether the server is started from the
  repository root or from ``backend/``;
- real environment variables always take precedence over .env values (this is
  what keeps Render's platform-provided variables authoritative);
- ``LLM_PROVIDER=xkiro`` remains supported (normalized to xai);
- tests never print, log, or otherwise expose secret values.

The module-level autouse fixture clears the service-related system variables
that ``tests/conftest.py`` blanks out, so the dotenv values actually reach the
settings object instead of being shadowed by the conftest empties.
"""

import textwrap
from pathlib import Path

import pytest

from app.config import Settings, dotenv_path
from app.runtime_config import (
    RuntimeConfigError,
    llm_is_configured,
    require_runtime_config,
    validate_runtime_config,
)

_SYSTEM_VARS_TO_CLEAR = (
    "CORS_ORIGINS",
    "DATABASE_URL",
    "ENVIRONMENT",
    "GEMINI_API_KEY",
    "LLM_PROVIDER",
    "XAI_API_KEY",
    "XAI_MODEL",
)


@pytest.fixture(autouse=True)
def _clear_system_service_vars(monkeypatch):
    for var in _SYSTEM_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)


def test_dotenv_path_is_absolute_backend_dotenv():
    path = dotenv_path()
    assert isinstance(path, Path)
    assert path.is_absolute()
    assert path.name == ".env"
    # Anchored to backend/ (the parent of app/), not to the CWD or repo root.
    assert path.parent.name == "backend"
    expected_backend = Path(__file__).resolve().parents[1]
    assert path.parent == expected_backend


def test_settings_config_env_file_is_the_absolute_backend_dotenv():
    env_file = Settings.model_config["env_file"]
    assert env_file == (str(dotenv_path()),)
    for candidate in env_file:
        assert Path(candidate).is_absolute()
        assert candidate.endswith(".env")


@pytest.fixture
def temp_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        textwrap.dedent(
            """\
            CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
            DATABASE_URL=postgresql+asyncpg://u:p@localhost:5432/discovery
            ENVIRONMENT=development
            LLM_PROVIDER=xkiro
            XAI_API_KEY=dotenv-xai-key
            XAI_MODEL=grok-test
            """
        ),
        encoding="utf-8",
    )
    return env


def test_settings_reads_values_from_dotenv(temp_dotenv):
    cfg = Settings(_env_file=str(temp_dotenv))
    assert cfg.llm_provider == "xkiro"
    assert cfg.xai_api_key == "dotenv-xai-key"
    assert cfg.xai_model == "grok-test"
    assert cfg.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert cfg.environment == "development"
    assert cfg.database_url == "postgresql+asyncpg://u:p@localhost:5432/discovery"
    # Fully configured development settings pass strict validation.
    assert validate_runtime_config(cfg) == []


def test_system_environment_precedes_dotenv(temp_dotenv, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "system-xai-key")
    cfg = Settings(_env_file=str(temp_dotenv))
    # System env wins over the .env value...
    assert cfg.xai_api_key == "system-xai-key"
    # ...while variables absent from the system env still come from .env.
    assert cfg.database_url == "postgresql+asyncpg://u:p@localhost:5432/discovery"
    assert cfg.llm_provider == "xkiro"


def test_default_settings_discover_real_backend_dotenv(monkeypatch):
    """End-to-end proof: default Settings() reads the actual backend/.env.

    The file is populated with disposable placeholder values and restored to
    its exact original bytes afterwards, so real credentials are never touched
    or exposed. A different CWD is simulated to prove CWD-independence.
    """
    real_path = dotenv_path()
    assert real_path.parent.exists()
    original = real_path.read_bytes() if real_path.exists() else b""
    monkeypatch.chdir(real_path.parent.parent.parent)  # repository root
    try:
        real_path.write_text(
            textwrap.dedent(
                """\
                DATABASE_URL=postgresql+asyncpg://u:p@localhost:5432/discovery
                ENVIRONMENT=development
                LLM_PROVIDER=xkiro
                XAI_API_KEY=discovery-test-key
                XAI_MODEL=grok-discovered
                """
            ),
            encoding="utf-8",
        )
        cfg = Settings()
        assert cfg.llm_provider == "xkiro"
        assert cfg.xai_api_key == "discovery-test-key"
        assert cfg.xai_model == "grok-discovered"
        assert cfg.database_url == "postgresql+asyncpg://u:p@localhost:5432/discovery"
    finally:
        real_path.write_bytes(original)


def test_default_config_is_cwd_independent(tmp_path, monkeypatch):
    # Launching from a far-away CWD must not change which file settings reads:
    # the configured path stays absolute and anchored to backend/.
    monkeypatch.chdir(tmp_path)
    env_file = Settings.model_config["env_file"]
    assert env_file == (str(dotenv_path()),)
    assert Path(env_file[0]).is_absolute()


def test_validation_output_never_exposes_secret_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "LLM_PROVIDER=xkiro\n"
        "XAI_API_KEY=super-secret-xai-token-abc\n"
        "DATABASE_URL=postgresql+asyncpg://owner:super-secret-db-pass@db.internal:5432/db\n",
        encoding="utf-8",
    )

    cfg = Settings(_env_file=str(env), DATABASE_URL="")
    problems = validate_runtime_config(cfg)
    joined = "\n".join(problems)
    assert "super-secret" not in joined
    assert "DATABASE_URL is not configured" in joined
    assert "db.internal" not in joined

    with pytest.raises(RuntimeConfigError) as excinfo:
        require_runtime_config(cfg)
    message = str(excinfo.value)
    assert "super-secret" not in message
    assert "db.internal" not in message


def test_xkiro_provider_is_treated_as_xai():
    # LLM_PROVIDER=xkiro maps to the xAI provider: with XAI_API_KEY set the
    # configuration is valid; without it the XAI error is reported.
    valid = Settings(
        ENVIRONMENT="development",
        LLM_PROVIDER="xkiro",
        XAI_API_KEY="some-xai-key",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db",
    )
    assert llm_is_configured(valid) is True
    assert validate_runtime_config(valid) == []

    missing_key = Settings(
        ENVIRONMENT="development",
        LLM_PROVIDER="xkiro",
        XAI_API_KEY="",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/db",
    )
    problems = validate_runtime_config(missing_key)
    assert len(problems) == 1
    assert "XAI_API_KEY is not configured" in problems[0]