"""Unit tests for the provider-independent LLM factory and abstraction."""

import pytest
from app.config import Settings
from app.llm import (
    GeminiLLMService,
    GeminiProvider,
    LLMProvider,
    LLMProviderError,
    LLMService,
    XAiLLMService,
    XAIProvider,
    get_llm_service,
)


def test_factory_defaults_to_xai():
    """Verify default provider is xAI when LLM_PROVIDER is not explicitly specified or is xai."""
    cfg = Settings(
        APP_NAME="test-app",
        LLM_PROVIDER="xai",
        XAI_API_KEY="test-xai-key",
        XAI_MODEL="grok-2-latest",
    )
    service = get_llm_service(cfg)
    assert isinstance(service, XAiLLMService)
    assert isinstance(service, XAIProvider)
    assert isinstance(service, LLMProvider)
    assert service.model == "grok-2-latest"
    assert service.is_configured is True


def test_factory_returns_gemini_when_configured():
    """Verify factory returns Gemini provider when LLM_PROVIDER=gemini."""
    cfg = Settings(
        APP_NAME="test-app",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="test-gemini-key",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    service = get_llm_service(cfg)
    assert isinstance(service, GeminiLLMService)
    assert isinstance(service, GeminiProvider)
    assert isinstance(service, LLMProvider)
    assert service.model == "gemini-3.8-flash"
    assert service.is_configured is True


def test_provider_aliases_and_subclassing():
    """Verify GeminiProvider and XAIProvider aliases are interchangeable."""
    assert GeminiProvider is GeminiLLMService
    assert XAIProvider is XAiLLMService
    assert issubclass(GeminiProvider, LLMProvider)
    assert issubclass(XAIProvider, LLMProvider)


def test_llm_service_alias_matches_factory():
    """Verify LLMService alias functions identically to get_llm_service."""
    cfg = Settings(
        APP_NAME="test-app",
        LLM_PROVIDER="xai",
        XAI_API_KEY="key",
    )
    assert isinstance(LLMService(cfg), XAiLLMService)
