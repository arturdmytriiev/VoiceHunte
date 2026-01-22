"""
Integration tests for Twilio webhook signature verification.

These tests verify that all Twilio webhook endpoints properly validate
the X-Twilio-Signature header and reject requests with invalid signatures.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app import main
from app.core.config import settings


def _compute_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Helper to compute valid Twilio signature."""
    validator = RequestValidator(auth_token)
    return validator.compute_signature(url, params)


def test_incoming_call_rejects_missing_signature() -> None:
    """Test that incoming call endpoint rejects requests without signature."""
    client = TestClient(main.app)

    with patch.object(settings, "twilio_auth_token", "test_auth_token"):
        response = client.post(
            "/twilio/incoming",
            data={
                "CallSid": "CA1234567890abcdef",
                "From": "+15555551234",
                "To": "+15555555678",
            },
            # No X-Twilio-Signature header
        )

    assert response.status_code == 403


def test_incoming_call_rejects_invalid_signature() -> None:
    """Test that incoming call endpoint rejects requests with invalid signature."""
    client = TestClient(main.app)

    with patch.object(settings, "twilio_auth_token", "test_auth_token"):
        response = client.post(
            "/twilio/incoming",
            data={
                "CallSid": "CA1234567890abcdef",
                "From": "+15555551234",
                "To": "+15555555678",
            },
            headers={"X-Twilio-Signature": "invalid_signature"},
        )

    assert response.status_code == 403


def test_incoming_call_accepts_valid_signature() -> None:
    """Test that incoming call endpoint accepts requests with valid signature."""
    client = TestClient(main.app)
    auth_token = "test_auth_token"

    params = {
        "CallSid": "CA1234567890abcdef",
        "From": "+15555551234",
        "To": "+15555555678",
    }

    # Compute valid signature
    # Note: TestClient uses http://testserver as base URL
    url = "http://testserver/twilio/incoming"
    signature = _compute_signature(url, params, auth_token)

    with patch.object(settings, "twilio_auth_token", auth_token):
        response = client.post(
            "/twilio/incoming",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert b"<Response>" in response.content


def test_voice_input_rejects_invalid_signature_with_twiml() -> None:
    """
    Test that voice input endpoint rejects invalid signatures
    and returns TwiML error message (not empty 403).
    """
    client = TestClient(main.app)

    with patch.object(settings, "twilio_auth_token", "test_auth_token"):
        response = client.post(
            "/twilio/voice",
            data={
                "CallSid": "CA1234567890abcdef",
                "SpeechResult": "Hello",
            },
            headers={"X-Twilio-Signature": "invalid_signature"},
        )

    # Should return 403 but with TwiML content
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    assert b"<Response>" in response.content
    assert b"could not verify" in response.content


def test_voice_input_accepts_valid_signature(clean_db, postgres_dsn: str) -> None:
    """Test that voice input endpoint accepts requests with valid signature."""
    main.store = main.ConversationStore(postgres_dsn)
    client = TestClient(main.app)
    auth_token = "test_auth_token"

    params = {
        "CallSid": "CA1234567890abcdef",
        "SpeechResult": "I want to make a reservation",
        "Confidence": "0.95",
    }

    url = "http://testserver/twilio/voice"
    signature = _compute_signature(url, params, auth_token)

    with patch.object(settings, "twilio_auth_token", auth_token):
        response = client.post(
            "/twilio/voice",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )

    assert response.status_code == 200
    assert b"<Response>" in response.content


def test_call_status_rejects_invalid_signature() -> None:
    """Test that call status endpoint rejects requests with invalid signature."""
    client = TestClient(main.app)

    with patch.object(settings, "twilio_auth_token", "test_auth_token"):
        response = client.post(
            "/twilio/status",
            data={
                "CallSid": "CA1234567890abcdef",
                "CallStatus": "completed",
            },
            headers={"X-Twilio-Signature": "invalid_signature"},
        )

    assert response.status_code == 403


def test_call_status_accepts_valid_signature() -> None:
    """Test that call status endpoint accepts requests with valid signature."""
    client = TestClient(main.app)
    auth_token = "test_auth_token"

    params = {
        "CallSid": "CA1234567890abcdef",
        "CallStatus": "completed",
    }

    url = "http://testserver/twilio/status"
    signature = _compute_signature(url, params, auth_token)

    with patch.object(settings, "twilio_auth_token", auth_token):
        response = client.post(
            "/twilio/status",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"


def test_signature_verification_respects_forwarded_headers() -> None:
    """
    Test that signature verification correctly uses X-Forwarded-Proto
    and X-Forwarded-Host headers (for reverse proxy scenarios).
    """
    client = TestClient(main.app)
    auth_token = "test_auth_token"

    params = {
        "CallSid": "CA1234567890abcdef",
        "From": "+15555551234",
        "To": "+15555555678",
    }

    # Signature should be computed using the forwarded URL
    url = "https://example.com/twilio/incoming"
    signature = _compute_signature(url, params, auth_token)

    with patch.object(settings, "twilio_auth_token", auth_token):
        response = client.post(
            "/twilio/incoming",
            data=params,
            headers={
                "X-Twilio-Signature": signature,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "example.com",
            },
        )

    assert response.status_code == 200
