"""xAI / Grok LLM service integration layer.

Provides a centralized, robust client interface to the xAI / Grok API.
Handles prompt execution, structured JSON output, exception mapping, and API key safeguards.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.config import Settings, settings
from app.timing import log_stage, start_timer

logger = logging.getLogger(__name__)


class XAiConfigurationError(Exception):
    """Raised when xAI client configuration is invalid or missing."""


class XAiAPIError(Exception):
    """Raised when xAI API request fails."""


class XAiLLMService:
    """Reusable service for communicating with xAI / Grok models.

    Adheres strictly to zero credential leaking, robust error wrapping,
    and structured generation support.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        config: Settings | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the xAI service.

        Args:
            api_key: Optional explicit xAI API key (defaults to config).
            model: Optional explicit model identifier (defaults to config).
            config: Optional Settings instance (defaults to global settings).
            base_url: Optional API endpoint base URL (defaults to config or https://api.x.ai/v1).
        """
        cfg = config or settings
        self._api_key = (api_key or cfg.xai_api_key or "").strip()
        self.model = (model or cfg.xai_model or "grok-2-latest").strip()
        self.base_url = (base_url or getattr(cfg, "xai_base_url", "https://api.x.ai/v1")).rstrip("/")
        self._http_timeout = getattr(cfg, "xai_request_timeout_seconds", 120)

    @property
    def is_configured(self) -> bool:
        """Check whether a non-empty API key is configured."""
        return bool(self._api_key)

    def _validate_configured(self) -> None:
        """Ensure the API key is configured before calling the remote API."""
        if not self._api_key:
            raise XAiConfigurationError(
                "xAI API key is not configured. Please set the XAI_API_KEY environment variable."
            )

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate text from xAI / Grok asynchronously.

        Args:
            prompt: User prompt string (must not be empty).
            system_instruction: Optional system instruction/persona.
            temperature: Optional sampling temperature.

        Returns:
            Model response text.

        Raises:
            ValueError: If prompt is empty or whitespace.
            XAiConfigurationError: If API key is missing.
            XAiAPIError: If the remote API call fails.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty or whitespace.")

        self._validate_configured()

        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt.strip()})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else 0.0,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        call_timer = start_timer()
        try:
            timeout = httpx.Timeout(self._http_timeout if self._http_timeout and self._http_timeout > 0 else 120.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            log_stage("xai.generate", call_timer.elapsed_ms(), ok=True, detail=f"model={self.model}")
            choices = data.get("choices") or []
            if not choices:
                raise XAiAPIError("xAI returned an empty choices list.")
            text_result = choices[0].get("message", {}).get("content", "") or ""
            return text_result.strip()
        except httpx.TimeoutException:
            logger.error("xAI API timed out after %s seconds: %s", self._http_timeout, self.model)
            log_stage("xai.generate", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model} TIMEOUT")
            raise XAiAPIError(
                f"xAI API call timed out after {self._http_timeout} seconds"
            ) from None
        except httpx.HTTPStatusError as e:
            logger.error("xAI HTTP error status=%s", e.response.status_code)
            log_stage("xai.generate", call_timer.elapsed_ms(), ok=False, detail=f"status={e.response.status_code}")
            try:
                err_body = e.response.json()
                err_msg = err_body.get("error", {}).get("message") or str(err_body)
            except Exception:
                err_msg = e.response.text[:200]
            raise XAiAPIError(f"xAI API call failed ({e.response.status_code}): {err_msg}") from e
        except XAiConfigurationError:
            raise
        except Exception as e:
            logger.error("Unexpected error during xAI generation: %s", type(e).__name__)
            log_stage("xai.generate", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model}")
            raise XAiAPIError(f"xAI generation error: {str(e)}") from e

    async def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        system_instruction: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Generate structured JSON response from xAI / Grok.

        Args:
            prompt: User prompt string.
            response_schema: Optional JSON schema dict for schema guidance.
            system_instruction: Optional system instruction.
            temperature: Optional sampling temperature.

        Returns:
            Parsed JSON object or array.

        Raises:
            ValueError: If prompt is empty or response is not valid JSON.
            XAiConfigurationError: If API key is missing.
            XAiAPIError: If the remote API call fails or fails JSON validation.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty or whitespace.")

        self._validate_configured()

        messages: list[dict[str, str]] = []
        effective_sys = system_instruction or "You are a helpful assistant."
        effective_sys += " You must respond strictly in valid JSON format without markdown code blocks."
        if response_schema:
            effective_sys += f" The response must strictly conform to this JSON schema: {json.dumps(response_schema)}"

        messages.append({"role": "system", "content": effective_sys})
        messages.append({"role": "user", "content": prompt.strip()})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else 0.0,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        call_timer = start_timer()
        try:
            timeout = httpx.Timeout(self._http_timeout if self._http_timeout and self._http_timeout > 0 else 120.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            log_stage("xai.generate_json", call_timer.elapsed_ms(), ok=True, detail=f"model={self.model}")
            choices = data.get("choices") or []
            if not choices:
                raise XAiAPIError("xAI returned an empty choices list.")
            raw_text = (choices[0].get("message", {}).get("content", "") or "").strip()
            if not raw_text:
                raise XAiAPIError("Empty response text returned by xAI model.")

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
        except httpx.TimeoutException:
            logger.error("xAI API timed out after %s seconds during JSON generation: %s", self._http_timeout, self.model)
            log_stage("xai.generate_json", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model} TIMEOUT")
            raise XAiAPIError(
                f"xAI JSON generation timed out after {self._http_timeout} seconds"
            ) from None
        except httpx.HTTPStatusError as e:
            logger.error("xAI HTTP error during JSON generation status=%s", e.response.status_code)
            log_stage("xai.generate_json", call_timer.elapsed_ms(), ok=False, detail=f"status={e.response.status_code}")
            try:
                err_body = e.response.json()
                err_msg = err_body.get("error", {}).get("message") or str(err_body)
            except Exception:
                err_msg = e.response.text[:200]
            raise XAiAPIError(f"xAI API call failed ({e.response.status_code}): {err_msg}") from e
        except json.JSONDecodeError as err:
            raise XAiAPIError(f"Failed to parse xAI response as JSON: {err}") from err
        except (XAiConfigurationError, XAiAPIError, ValueError):
            raise
        except Exception as e:
            logger.error("Unexpected error during xAI JSON generation: %s", type(e).__name__)
            log_stage("xai.generate_json", call_timer.elapsed_ms(), ok=False, detail=f"model={self.model}")
            raise XAiAPIError(f"xAI JSON generation error: {str(e)}") from e
