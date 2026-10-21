"""Unit tests for OpenAI-compatible LLM service and configuration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.llm import LLMService


@pytest.mark.asyncio
async def test_llm_service_initialization(test_settings: Settings):
    service = LLMService(settings=test_settings)
    assert service.settings.OPENAI_BASE_URL == "http://mock-llm-server:11434/v1"
    assert service.settings.LLM_MODEL == "qwen-test"
    assert service.model == "qwen-test"


@pytest.mark.asyncio
async def test_llm_service_completion_mocked(test_settings: Settings):
    service = LLMService(settings=test_settings)

    mock_choice = MagicMock()
    mock_choice.message.content = "Summary: Boxed warning updated with IMNM autoimmune risk."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(
        service.client.chat.completions,
        "create",
        new=AsyncMock(return_value=mock_response),
    ) as mock_create:
        result = await service.complete(
            prompt="Analyze the following label changes: ...",
            system_prompt="You are a regulatory affairs analyst.",
        )

        assert "IMNM" in result
        mock_create.assert_awaited_once()
        call_kwargs = mock_create.await_args.kwargs
        assert call_kwargs["model"] == "qwen-test"
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"
