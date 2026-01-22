from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app import main
from app.tts.openai_tts import stream_tts


def test_tts_stream_endpoint_success() -> None:
    """Test TTS streaming endpoint returns audio."""
    client = TestClient(main.app)

    with patch("app.tts.openai_tts.stream_tts") as mock_stream:
        mock_stream.return_value = iter([b"fake", b"audio", b"data"])

        response = client.post(
            "/tts/stream",
            json={
                "text": "Hello world",
                "voice": "alloy",
                "model": "tts-1",
                "response_format": "mp3",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert b"fakeaudiodata" in response.content


def test_tts_stream_endpoint_invalid_voice() -> None:
    """Test TTS endpoint with invalid voice."""
    client = TestClient(main.app)

    with patch("app.tts.openai_tts.stream_tts") as mock_stream:
        mock_stream.side_effect = ValueError("Unsupported voice: invalid")

        response = client.post(
            "/tts/stream",
            json={
                "text": "Hello world",
                "voice": "invalid",
            },
        )

        assert response.status_code == 500
        assert "TTS generation failed" in response.json()["detail"]


def test_tts_stream_endpoint_missing_text() -> None:
    """Test TTS endpoint without text."""
    client = TestClient(main.app)

    response = client.post(
        "/tts/stream",
        json={"voice": "alloy"},
    )

    assert response.status_code == 422


def test_stream_tts_requires_api_key() -> None:
    """Test that stream_tts raises error without API key."""
    with patch("app.tts.openai_tts.settings") as mock_settings:
        mock_settings.openai_api_key = None

        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
            list(stream_tts("Hello"))


def test_stream_tts_validates_voice() -> None:
    """Test that stream_tts validates voice parameter."""
    with patch("app.tts.openai_tts.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"

        with pytest.raises(ValueError, match="Unsupported voice"):
            list(stream_tts("Hello", voice="invalid_voice"))


def test_stream_tts_validates_model() -> None:
    """Test that stream_tts validates model parameter."""
    with patch("app.tts.openai_tts.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"

        with pytest.raises(ValueError, match="Unsupported model"):
            list(stream_tts("Hello", model="invalid_model"))


def test_stream_tts_validates_format() -> None:
    """Test that stream_tts validates response_format parameter."""
    with patch("app.tts.openai_tts.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"

        with pytest.raises(ValueError, match="Unsupported format"):
            list(stream_tts("Hello", response_format="invalid_format"))


def test_stream_tts_validates_speed() -> None:
    """Test that stream_tts validates speed parameter."""
    with patch("app.tts.openai_tts.settings") as mock_settings:
        mock_settings.openai_api_key = "test-key"

        with pytest.raises(ValueError, match="Speed must be between"):
            list(stream_tts("Hello", speed=5.0))

        with pytest.raises(ValueError, match="Speed must be between"):
            list(stream_tts("Hello", speed=0.1))
