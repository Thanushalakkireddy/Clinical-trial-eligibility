from pathlib import Path
from typing import List, Union

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application configuration settings."""

    app_name: str = Field(default="clinical-trial-eligibility-api", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    cors_origins: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return []

    # Gemini and LLM settings
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.8-flash", alias="GEMINI_MODEL")

    # Storage settings
    pdf_storage_dir: str = Field(default="./storage/pdfs", alias="PDF_STORAGE_DIR")
    max_upload_size_bytes: int = Field(default=20 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")  # 20MB

    @field_validator(
        "debug",
        "port",
        "max_upload_size_bytes",
        "database_command_timeout_seconds",
        "checkpointer_connect_timeout_seconds",
        "checkpointer_setup_timeout_seconds",
        "gemini_request_timeout_seconds",
        "embedding_model_load_timeout_seconds",
        "rag_retrieve_timeout_seconds",
        "workflow_timeout_seconds",
        mode="before",
    )
    @classmethod
    def empty_string_falls_back_to_default(cls, v, info: ValidationInfo):
        """Treat blank .env values as 'not set' so defaults apply.

        .env files routinely carry bare keys (e.g. ``MAX_UPLOAD_SIZE_BYTES=``);
        pydantic would otherwise fail to parse empty strings as int/bool.
        """
        if isinstance(v, str) and not v.strip():
            default = cls.model_fields[info.field_name].default
            return default
        return v

    # Database settings
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    vector_store_backend: str = Field(default="faiss", alias="VECTOR_STORE_BACKEND")
    # Bounded database operation timeout. Applied as the asyncpg per-command
    # timeout so slow/broken flush(), commit(), and query round-trips fail fast
    # instead of leaving requests Pending indefinitely. 0 disables the limit.
    database_command_timeout_seconds: int = Field(
        default=60, alias="DATABASE_COMMAND_TIMEOUT_SECONDS"
    )
    # Bounded LangGraph PostgreSQL checkpointer connection/setup deadlines.
    # These let a sleeping/unreachable Render Postgres fail fast and fall back
    # to the deterministic workflow instead of hanging forever.
    checkpointer_connect_timeout_seconds: int = Field(
        default=20, alias="CHECKPOINTER_CONNECT_TIMEOUT_SECONDS"
    )
    checkpointer_setup_timeout_seconds: int = Field(
        default=30, alias="CHECKPOINTER_SETUP_TIMEOUT_SECONDS"
    )
    # Gemini mutation deadline. google-genai's HttpOptions.timeout defaults to
    # None (no timeout at all), so bound every LLM call explicitly. 0 keeps the
    # SDK default.
    gemini_request_timeout_seconds: int = Field(
        default=120, alias="GEMINI_REQUEST_TIMEOUT_SECONDS"
    )
    # Bounded SentenceTransformer model load deadline. HuggingFace model
    # download/load is a synchronous, network-dependent call that used to block
    # the async event loop indefinitely (the classic "request stays Pending
    # forever"). When exceeded the RAG layer degrades to its deterministic
    # fallback instead of stalling the request. 0 keeps the blocking load.
    embedding_model_load_timeout_seconds: int = Field(
        default=30, alias="EMBEDDING_MODEL_LOAD_TIMEOUT_SECONDS"
    )
    # Bounded total deadline for RAG service init + FAISS/metadata retrieval
    # inside the workflow. Runs off the event loop in a worker thread; this
    # caps how long the retrieve step may take.
    rag_retrieve_timeout_seconds: int = Field(
        default=60, alias="RAG_RETRIEVE_TIMEOUT_SECONDS"
    )
    # Bounded total deadline for a single workflow evaluation request. Guarantees
    # POST /api/v1/workflow/evaluate always returns (a result or a clean error)
    # instead of hanging indefinitely no matter what a downstream component does.
    workflow_timeout_seconds: int = Field(
        default=180, alias="WORKFLOW_TIMEOUT_SECONDS"
    )

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
