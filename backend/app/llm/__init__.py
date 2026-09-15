"""LLM integration package."""

from typing import Union
from app.config import Settings, settings
from app.llm.gemini_service import (
    GeminiAPIError,
    GeminiConfigurationError,
    GeminiLLMService,
)
from app.llm.xai_service import (
    XAiAPIError,
    XAiConfigurationError,
    XAiLLMService,
)

LLMServiceType = Union[XAiLLMService, GeminiLLMService]


def get_llm_service(config: Settings | None = None) -> LLMServiceType:
    """Factory returning the active LLM service based on LLM_PROVIDER setting.

    Defaults to XAiLLMService when LLM_PROVIDER='xai'.
    Falls back to GeminiLLMService when LLM_PROVIDER='gemini'.
    """
    cfg = config or settings
    provider = (getattr(cfg, "llm_provider", None) or "xai").strip().lower()
    if provider == "gemini":
        return GeminiLLMService(config=cfg)
    return XAiLLMService(config=cfg)


__all__ = [
    "XAiLLMService",
    "XAiConfigurationError",
    "XAiAPIError",
    "GeminiLLMService",
    "GeminiConfigurationError",
    "GeminiAPIError",
    "get_llm_service",
    "LLMServiceType",
]

