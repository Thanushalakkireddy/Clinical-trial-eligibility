"""LLM integration package providing provider-independent abstraction."""

from typing import Union
from app.config import Settings, settings
from app.llm.base import (
    LLMConfigurationError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMTimeoutError,
)
from app.llm.gemini_service import (
    GeminiAPIError,
    GeminiConfigurationError,
    GeminiLLMService,
    GeminiRateLimitError,
    GeminiResponseParsingError,
    GeminiTimeoutError,
)
from app.llm.xai_service import (
    XAiAPIError,
    XAiConfigurationError,
    XAiLLMService,
    XAiRateLimitError,
    XAiResponseParsingError,
    XAiTimeoutError,
)

# Aliases requested by requirements
GeminiProvider = GeminiLLMService
XAIProvider = XAiLLMService

LLMServiceType = Union[XAiLLMService, GeminiLLMService, LLMProvider]


def get_llm_service(config: Settings | None = None) -> LLMProvider:
    """Factory returning the active LLM provider based on LLM_PROVIDER setting.

    Defaults to XAiLLMService (XAIProvider) when LLM_PROVIDER='xai'.
    Falls back to GeminiLLMService (GeminiProvider) when LLM_PROVIDER='gemini'.
    """
    cfg = config or settings
    provider = (getattr(cfg, "llm_provider", None) or "xai").strip().lower()
    if provider == "gemini":
        return GeminiLLMService(config=cfg)
    return XAiLLMService(config=cfg)


# Reusable service class / factory alias
LLMService = get_llm_service

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMConfigurationError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMResponseParsingError",
    "XAiLLMService",
    "XAIProvider",
    "XAiConfigurationError",
    "XAiAPIError",
    "XAiTimeoutError",
    "XAiRateLimitError",
    "XAiResponseParsingError",
    "GeminiLLMService",
    "GeminiProvider",
    "GeminiConfigurationError",
    "GeminiAPIError",
    "GeminiTimeoutError",
    "GeminiRateLimitError",
    "GeminiResponseParsingError",
    "get_llm_service",
    "LLMService",
    "LLMServiceType",
]

