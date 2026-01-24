from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy dependencies that aren't needed for unit tests
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["qdrant_client"] = MagicMock()

from app.core.errors import ExternalAPIError


def test_chat_completion_raises_without_api_key() -> None:
    """Test that chat_completion raises RuntimeError without API key."""
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.openai_api_key = None

        from app.llm import openai_chat

        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
            openai_chat.chat_completion("test prompt")


def test_chat_completion_success() -> None:
    """Test successful chat completion request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Test response"}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.llm.openai_chat.settings") as mock_settings:
        mock_settings.openai_api_key = "test-api-key"
        mock_settings.llm_intent_model = "gpt-4o-mini"

        with patch("app.llm.openai_chat.requests.post", return_value=mock_response):
            from app.llm.openai_chat import chat_completion

            result = chat_completion("test prompt")

            assert result == "Test response"


def test_chat_completion_extracts_content() -> None:
    """Test that chat_completion correctly extracts content from response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"intent": "create_reservation", "entities": null, "language": "en"}'
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.llm.openai_chat.settings") as mock_settings:
        mock_settings.openai_api_key = "test-api-key"
        mock_settings.llm_intent_model = "gpt-4o-mini"

        with patch("app.llm.openai_chat.requests.post", return_value=mock_response):
            from app.llm.openai_chat import chat_completion

            result = chat_completion("I want to book a table")

            assert "create_reservation" in result
            assert "language" in result
