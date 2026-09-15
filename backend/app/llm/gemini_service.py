"""Gemini LLM service integration layer.

Provides a centralized, robust client interface to the official Google Gemini SDK.
Handles prompt execution, structured JSON output, exception mapping, and API key safeguards.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import Settings, settings
from app.llm.base import (
    LLMConfigurationError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMTimeoutError,
)
from app.timing import log_stage, start_timer

logger = logging.getLogger(__name__)


class GeminiConfigurationError(LLMConfigurationError):
    """Raised when Gemini client configuration is invalid or missing."""


class GeminiAPIError(LLMProviderError):
    """Raised when Gemini API request fails."""


class GeminiTimeoutError(LLMTimeoutError, GeminiAPIError):
    """Raised when Gemini request times out."""


class GeminiRateLimitError(LLMRateLimitError, GeminiAPIError):
    """Raised when Gemini rate limit is exceeded."""


class GeminiResponseParsingError(LLMResponseParsingError, GeminiAPIError):
    """Raised when parsing Gemini response fails."""


class GeminiLLMService(LLMProvider):
    """Reusable service for communicating with Google Gemini models.
    
    Adheres strictly to zero credential leaking, robust error wrapping,
    and structured generation support.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        config: Settings | None = None,
    ) -> None:
        """Initialize the Gemini service.

        Args:
            api_key: Optional explicit Gemini API key (defaults to config).
            model: Optional explicit model identifier (defaults to config).
            config: Optional Settings instance (defaults to global settings).
        """
        cfg = config or settings
        self._api_key = (api_key or cfg.gemini_api_key or "").strip()
        self.model = (model or cfg.gemini_model or "gemini-3.8-flash").strip()
        self._http_timeout = cfg.gemini_request_timeout_seconds
        self._client: genai.Client | None = None

    @property
    def is_configured(self) -> bool:
        """Check whether a non-empty API key is configured."""
        return bool(self._api_key)

    def _get_client(self) -> genai.Client:
        """Lazily initialize and retrieve the underlying GenAI client.

        Raises:
            GeminiConfigurationError: If no API key is provided.
        """
        if not self._api_key:
            raise GeminiConfigurationError(
                "Gemini API key is not configured. Please set the GEMINI_API_KEY environment variable."
            )
        if self._client is None:
            # google-genai defaults HttpOptions.timeout to None (no deadline),
            # so a blackholed network would leave the request hanging forever.
            # Bound every call to the configured timeout to fail fast instead.
            http_options = None
            if self._http_timeout and self._http_timeout > 0:
                http_options = types.HttpOptions(timeout=self._http_timeout)
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=http_options,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate text from Gemini asynchronously.

        Args:
            prompt: User prompt string (must not be empty).
            system_instruction: Optional system instruction/persona.
            temperature: Optional sampling temperature.

        Returns:
            Model response text.

        Raises:
            ValueError: If prompt is empty or whitespace.
            GeminiConfigurationError: If API key is missing.
            GeminiAPIError: If the remote API call fails.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty or whitespace.")

        client = self._get_client()

        config_args: dict[str, Any] = {}
        if system_instruction:
            config_args["system_instruction"] = system_instruction
        if temperature is not None:
            config_args["temperature"] = temperature

        config = types.GenerateContentConfig(**config_args) if config_args else None

        try:
            # Client aio provides non-blocking asynchronous calls. Wrap the
            # await in asyncio.wait_for so a request can never hang forever,
            # even if HttpOptions.timeout is not honored by the transport.
            call_timer = start_timer()
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt.strip(),
                    config=config,
                ),
                timeout=self._http_timeout if self._http_timeout and self._http_timeout > 0 else None,
            )
            log_stage("gemini.generate", call_timer.elapsed_ms(), ok=True, detail=f"model={self.model}")
            text_result = getattr(response, "text", None) or ""
            return text_result.strip()
        except asyncio.TimeoutError:
            logger.error("Gemini API timed out after %s seconds: %s", self._http_timeout, type(self.model).__name__)
            log_stage("gemini.generate", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model} TIMEOUT")
            raise GeminiAPIError(
                f"Gemini API call timed out after {self._http_timeout} seconds"
            ) from None
        except APIError as e:
            # Mask any credentials and re-raise structured domain error
            logger.error("Gemini API error occurred: %s", type(e).__name__)
            log_stage("gemini.generate", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model}")
            raise GeminiAPIError(f"Gemini API call failed: {e.message}") from e
        except GeminiConfigurationError:
            raise
        except Exception as e:
            logger.error("Unexpected error during Gemini generation: %s", type(e).__name__)
            log_stage("gemini.generate", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model}")
            raise GeminiAPIError(f"Gemini generation error: {str(e)}") from e

    async def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        system_instruction: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Generate structured JSON response from Gemini.

        Args:
            prompt: User prompt string.
            response_schema: Optional JSON schema dict for schema enforcement.
            system_instruction: Optional system instruction.
            temperature: Optional sampling temperature.

        Returns:
            Parsed JSON object or array.

        Raises:
            ValueError: If prompt is empty or response is not valid JSON.
            GeminiConfigurationError: If API key is missing.
            GeminiAPIError: If the remote API call fails or fails JSON validation.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty or whitespace.")

        client = self._get_client()

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
        }
        if response_schema:
            config_kwargs["response_schema"] = response_schema
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if temperature is not None:
            config_kwargs["temperature"] = temperature

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            call_timer = start_timer()
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt.strip(),
                    config=config,
                ),
                timeout=self._http_timeout if self._http_timeout and self._http_timeout > 0 else None,
            )
            log_stage("gemini.generate_json", call_timer.elapsed_ms(), ok=True, detail=f"model={self.model}")
            raw_text = (getattr(response, "text", None) or "").strip()
            if not raw_text:
                raise GeminiAPIError("Empty response text returned by Gemini model.")
            
            # Clean possible markdown code fences if model wrapped response
            cleaned_text = raw_text
            if cleaned_text.startswith("```"):
                lines = cleaned_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_text = "\n".join(lines).strip()

            return json.loads(cleaned_text)
        except asyncio.TimeoutError:
            logger.error("Gemini API timed out after %s seconds during JSON generation: %s", self._http_timeout, type(self.model).__name__)
            log_stage("gemini.generate_json", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model} TIMEOUT")
            raise GeminiAPIError(
                f"Gemini JSON generation timed out after {self._http_timeout} seconds"
            ) from None
        except json.JSONDecodeError as err:
            raise GeminiAPIError(f"Failed to parse Gemini response as JSON: {err}") from err
        except APIError as e:
            logger.error("Gemini API error during JSON generation: %s", type(e).__name__)
            log_stage("gemini.generate_json", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model}")
            raise GeminiAPIError(f"Gemini API call failed: {e.message}") from e
        except (GeminiConfigurationError, GeminiAPIError, ValueError):
            raise
        except Exception as e:
            logger.error("Unexpected error during Gemini JSON generation: %s", type(e).__name__)
            log_stage("gemini.generate_json", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model}")
            raise GeminiAPIError(f"Gemini JSON generation error: {str(e)}") from e
