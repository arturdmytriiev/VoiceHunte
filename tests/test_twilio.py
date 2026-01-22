from __future__ import annotations

from fastapi.testclient import TestClient

from app import main


def test_twilio_incoming_call() -> None:
    """Test incoming Twilio call webhook."""
    client = TestClient(main.app)

    response = client.post(
        "/twilio/incoming",
        data={
            "CallSid": "CA1234567890abcdef",
            "From": "+15555551234",
            "To": "+15555555678",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert b"<Response>" in response.content
    assert b"<Gather" in response.content
    assert b"Welcome to our restaurant" in response.content


def test_twilio_voice_input_with_speech(clean_db, postgres_dsn: str) -> None:
    """Test Twilio voice input processing."""
    main.store = main.ConversationStore(postgres_dsn)
    client = TestClient(main.app)

    response = client.post(
        "/twilio/voice",
        data={
            "CallSid": "CA1234567890abcdef",
            "SpeechResult": "I want to make a reservation for 2 people",
            "Confidence": "0.95",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert b"<Response>" in response.content
    assert b"<Say" in response.content


def test_twilio_voice_input_without_speech() -> None:
    """Test Twilio voice input without speech result."""
    client = TestClient(main.app)

    response = client.post(
        "/twilio/voice",
        data={
            "CallSid": "CA1234567890abcdef",
            "SpeechResult": "",
            "Confidence": "0.0",
        },
    )

    assert response.status_code == 200
    assert b"<Response>" in response.content
    assert b"didn't catch that" in response.content


def test_twilio_status_callback() -> None:
    """Test Twilio status callback webhook."""
    client = TestClient(main.app)

    response = client.post(
        "/twilio/status",
        data={
            "CallSid": "CA1234567890abcdef",
            "CallStatus": "completed",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert b"<Response>" in response.content
