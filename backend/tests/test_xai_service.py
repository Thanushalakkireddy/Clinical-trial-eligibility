"""Unit tests for XAiLLMService (xAI / Grok).

All tests utilize mocked HTTP responses and DO NOT execute external API requests.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import json
import httpx
import pytest

from app.config import Settings
from app.llm.base import (
    LLMConfigurationError,
    LLMProvider,
    LLMProviderError,
    LLMTimeoutError,
)
from app.llm.xai_service import (
    XAiAPIError,
    XAiConfigurationError,
    XAiLLMService,
)


def test_service_initialization_with_config():
    """Verify XAiLLMService can be initialized from custom settings or explicit args."""
    custom_settings = Settings(
        APP_NAME="test-app",
        LLM_PROVIDER="xai",
        XAI_API_KEY="test-xai-mock-key",
        XAI_MODEL="grok-2-latest",
    )
    service = XAiLLMService(config=custom_settings)
    assert service.is_configured is True
    assert service.model == "grok-2-latest"
    assert isinstance(service, LLMProvider)

    # Explicit override test
    custom_service = XAiLLMService(api_key="override-key", model="grok-2-mini")
    assert custom_service.is_configured is True
    assert custom_service.model == "grok-2-mini"


def test_missing_api_key_handled_correctly():
    """Verify missing API key raises XAiConfigurationError upon client request."""
    custom_settings = Settings(
        APP_NAME="test-app",
        XAI_API_KEY="",
    )
    service = XAiLLMService(config=custom_settings)
    assert service.is_configured is False

    with pytest.raises(XAiConfigurationError, match="xAI API key is not configured"):
        service._validate_configured()
    assert issubclass(XAiConfigurationError, LLMConfigurationError)


@pytest.mark.asyncio
async def test_empty_prompt_is_rejected():
    """Verify empty or whitespace prompt raises ValueError."""
    service = XAiLLMService(api_key="mock-key")

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await service.generate("")

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await service.generate("   \n\t  ")

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await service.generate_json("")


@pytest.mark.asyncio
async def test_successful_text_generation():
    """Verify successful text generation returns model output without leaking credentials."""
    secret_key = "xai-secret-key-12345"
    service = XAiLLMService(api_key=secret_key, model="grok-2-latest")

    mock_response_data = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Protocol extracted criteria: Age >= 18.",
                }
            }
        ],
    }

    mock_post_response = MagicMock(spec=httpx.Response)
    mock_post_response.status_code = 200
    mock_post_response.json.return_value = mock_response_data
    mock_post_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_post_response

        result = await service.generate(
            prompt="Extract protocol criteria",
            system_instruction="You are a clinical protocol parser.",
        )

        assert result == "Protocol extracted criteria: Age >= 18."
        mock_post.assert_awaited_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "grok-2-latest"
        assert "Extract protocol criteria" in call_kwargs["json"]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_api_failure_converted_to_safe_error():
    """Verify underlying HTTP failure is converted into a safe domain XAiAPIError."""
    secret_key = "xai-secret-key-super-secret"
    service = XAiLLMService(api_key=secret_key)

    mock_request = httpx.Request("POST", "https://api.x.ai/v1/chat/completions")
    mock_resp = httpx.Response(500, request=mock_request, json={"error": {"message": "Internal Server Error"}})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with pytest.raises(XAiAPIError) as exc_info:
            await service.generate(prompt="Hello")

        # Ensure secret key is NEVER exposed in the error message
        assert secret_key not in str(exc_info.value)
        assert issubclass(XAiAPIError, LLMProviderError)


@pytest.mark.asyncio
async def test_timeout_converted_to_safe_error():
    """Verify timeout is converted into XAiAPIError / LLMTimeoutError."""
    service = XAiLLMService(api_key="mock-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Connection timed out")

        with pytest.raises(XAiAPIError, match="timed out"):
            await service.generate(prompt="Hello")


@pytest.mark.asyncio
async def test_structured_json_response_handling():
    """Verify structured JSON generation parses and returns dict or list properly."""
    service = XAiLLMService(api_key="mock-key-12345")

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "criteria": [{"id": "INC_01", "name": "Age >= 18"}],
                        "eligible": True,
                    }),
                }
            }
        ]
    }

    mock_post_response = MagicMock(spec=httpx.Response)
    mock_post_response.status_code = 200
    mock_post_response.json.return_value = mock_response_data
    mock_post_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_post_response

        result = await service.generate_json(
            prompt="Evaluate criteria",
            response_schema={"type": "object"},
        )

        assert isinstance(result, dict)
        assert result["eligible"] is True
        assert len(result["criteria"]) == 1
        assert result["criteria"][0]["id"] == "INC_01"


@pytest.mark.asyncio
async def test_structured_json_with_code_fences():
    """Verify structured JSON generation handles markdown-wrapped responses gracefully."""
    service = XAiLLMService(api_key="mock-key-12345")

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "```json\n{\"status\": \"OK\"}\n```",
                }
            }
        ]
    }

    mock_post_response = MagicMock(spec=httpx.Response)
    mock_post_response.status_code = 200
    mock_post_response.json.return_value = mock_response_data
    mock_post_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_post_response

        result = await service.generate_json(prompt="Status check")
        assert result == {"status": "OK"}
