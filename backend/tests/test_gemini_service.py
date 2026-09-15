"""Unit tests for GeminiLLMService.

All tests utilize mocked responses and DO NOT execute external API requests.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.config import Settings
from app.llm.gemini_service import (
    GeminiAPIError,
    GeminiConfigurationError,
    GeminiLLMService,
)


def test_service_initialization_with_config():
    """Verify GeminiLLMService can be initialized from custom settings or explicit args."""
    custom_settings = Settings(
        APP_NAME="test-app",
        GEMINI_API_KEY="test-key-mock",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    service = GeminiLLMService(config=custom_settings)
    assert service.is_configured is True
    assert service.model == "gemini-3.8-flash"

    # Explicit override test
    custom_service = GeminiLLMService(api_key="override-key", model="gemini-3.1-pro-preview")
    assert custom_service.is_configured is True
    assert custom_service.model == "gemini-3.1-pro-preview"


def test_missing_api_key_handled_correctly():
    """Verify missing API key raises GeminiConfigurationError upon client request."""
    custom_settings = Settings(
        APP_NAME="test-app",
        GEMINI_API_KEY="",
    )
    service = GeminiLLMService(config=custom_settings)
    assert service.is_configured is False

    with pytest.raises(GeminiConfigurationError, match="Gemini API key is not configured"):
        service._get_client()


@pytest.mark.asyncio
async def test_empty_prompt_is_rejected():
    """Verify empty or whitespace prompt raises ValueError."""
    service = GeminiLLMService(api_key="mock-key")

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await service.generate("")

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await service.generate("   \n\t  ")

    with pytest.raises(ValueError, match="Prompt must not be empty"):
        await service.generate_json("")


@pytest.mark.asyncio
async def test_successful_text_generation():
    """Verify successful text generation returns model output without leaking credentials."""
    service = GeminiLLMService(api_key="mock-key-12345")

    mock_response = MagicMock()
    mock_response.text = "Protocol extracted criteria: Age >= 18."

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(service, "_get_client", return_value=mock_client):
        result = await service.generate(
            prompt="Extract protocol criteria",
            system_instruction="You are a clinical protocol parser.",
        )

        assert result == "Protocol extracted criteria: Age >= 18."
        mock_client.aio.models.generate_content.assert_awaited_once()
        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == service.model
        assert call_kwargs["contents"] == "Extract protocol criteria"


@pytest.mark.asyncio
async def test_api_failure_converted_to_safe_error():
    """Verify underlying API failure is converted into a safe domain GeminiAPIError."""
    service = GeminiLLMService(api_key="mock-key-12345")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("Connection timeout or rate limit")
    )

    with patch.object(service, "_get_client", return_value=mock_client):
        with pytest.raises(GeminiAPIError, match="Gemini generation error: Connection timeout"):
            await service.generate(prompt="Hello")


@pytest.mark.asyncio
async def test_structured_json_response_handling():
    """Verify structured JSON generation parses and returns dict or list properly."""
    service = GeminiLLMService(api_key="mock-key-12345")

    mock_response = MagicMock()
    mock_response.text = '{"criteria": [{"id": "INC_01", "name": "Age >= 18"}], "eligible": true}'

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(service, "_get_client", return_value=mock_client):
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
    service = GeminiLLMService(api_key="mock-key-12345")

    mock_response = MagicMock()
    mock_response.text = "```json\n{\"status\": \"OK\"}\n```"

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch.object(service, "_get_client", return_value=mock_client):
        result = await service.generate_json(prompt="Status check")
        assert result == {"status": "OK"}
