"""Provider-independent LLM abstraction layer.

Defines the common interface and exception hierarchy for LLM providers
(xAI / Grok, Gemini, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Union


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""


class LLMConfigurationError(LLMProviderError):
    """Raised when an LLM provider is misconfigured or missing credentials."""


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM provider request times out."""


class LLMRateLimitError(LLMProviderError):
    """Raised when an LLM provider rate limit or quota is exceeded."""


class LLMResponseParsingError(LLMProviderError):
    """Raised when parsing an LLM response (e.g. structured JSON) fails."""


class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    model: str = ""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has valid credentials configured."""
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Generate text response from the provider.

        Args:
            prompt: User prompt.
            system_instruction: Optional system instruction.
            temperature: Sampling temperature (default 0.0 for deterministic output).

        Returns:
            Generated text string.
        """
        ...

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        system_instruction: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Generate structured JSON response conforming to optional schema.

        Args:
            prompt: User prompt.
            response_schema: Optional JSON schema.
            system_instruction: Optional system instruction.
            temperature: Sampling temperature.

        Returns:
            Parsed JSON object or array.
        """
        ...
