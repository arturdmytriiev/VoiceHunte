"""
Tests for Pydantic validation and sanitization of incoming data.

Verifies that:
- All input is sanitized (control chars removed, trimmed, length limited)
- Phone numbers are normalized to E.164 format
- Invalid payloads return 422 with clear error messages
- No raw request.form()/request.json() data reaches business logic
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.twilio.models import (
    TwilioCallStatusPayload,
    TwilioIncomingCallPayload,
    TwilioVoicePayload,
    normalize_phone_payload,
    sanitize_optional_payload,
    sanitize_text_payload,
)


class TestTextSanitization:
    """Test text sanitization functions."""

    def test_sanitize_text_strips_whitespace(self) -> None:
        """Test that text is stripped of leading/trailing whitespace."""
        result = sanitize_text_payload("  hello world  ")
        assert result == "hello world"

    def test_sanitize_text_removes_control_chars(self) -> None:
        """Test that control characters are removed."""
        result = sanitize_text_payload("hello\x00\x01\x1f\x7fworld")
        assert result == "helloworld"

    def test_sanitize_text_enforces_max_length(self) -> None:
        """Test that text exceeding max length raises ValueError."""
        with pytest.raises(ValueError, match="too long"):
            sanitize_text_payload("a" * 5000, max_length=4000)

    def test_sanitize_text_rejects_empty_after_strip(self) -> None:
        """Test that text that's empty after stripping raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            sanitize_text_payload("   ")

    def test_sanitize_optional_text_allows_none(self) -> None:
        """Test that optional sanitization allows None."""
        result = sanitize_optional_payload(None)
        assert result is None

    def test_sanitize_optional_text_sanitizes_non_none(self) -> None:
        """Test that optional sanitization sanitizes non-None values."""
        result = sanitize_optional_payload("  test\x00  ")
        assert result == "test"


class TestPhoneNormalization:
    """Test phone number normalization to E.164 format."""

    def test_normalize_phone_with_plus(self) -> None:
        """Test normalization of phone with + prefix."""
        result = normalize_phone_payload("+1234567890")
        assert result == "+1234567890"

    def test_normalize_phone_without_plus(self) -> None:
        """Test normalization adds + prefix if missing."""
        result = normalize_phone_payload("1234567890")
        assert result == "+1234567890"

    def test_normalize_phone_removes_formatting(self) -> None:
        """Test that formatting characters are removed."""
        result = normalize_phone_payload("+1 (234) 567-890")
        assert result == "+1234567890"

    def test_normalize_phone_removes_spaces(self) -> None:
        """Test that spaces are removed."""
        result = normalize_phone_payload("+1 234 567 890")
        assert result == "+1234567890"

    def test_normalize_phone_rejects_too_short(self) -> None:
        """Test that phone numbers < 8 digits are rejected."""
        with pytest.raises(ValueError, match="Invalid phone number"):
            normalize_phone_payload("123456")

    def test_normalize_phone_rejects_too_long(self) -> None:
        """Test that phone numbers > 15 digits are rejected."""
        with pytest.raises(ValueError, match="Invalid phone number"):
            normalize_phone_payload("1234567890123456")

    def test_normalize_phone_rejects_non_digits(self) -> None:
        """Test that phone numbers with letters are rejected."""
        with pytest.raises(ValueError, match="Invalid phone number"):
            normalize_phone_payload("123abc7890")

    def test_normalize_phone_allows_none(self) -> None:
        """Test that None is allowed for optional phone fields."""
        result = normalize_phone_payload(None)
        assert result is None


class TestTwilioIncomingCallPayload:
    """Test TwilioIncomingCallPayload validation."""

    def test_valid_payload(self) -> None:
        """Test that valid payload is accepted."""
        payload = TwilioIncomingCallPayload(
            CallSid="CA1234567890abcdef",
            From="+15555551234",
            To="+15555555678",
        )
        assert payload.CallSid == "CA1234567890abcdef"
        assert payload.From == "+15555551234"
        assert payload.To == "+15555555678"

    def test_call_sid_sanitized(self) -> None:
        """Test that CallSid is sanitized."""
        payload = TwilioIncomingCallPayload(
            CallSid="  CA123\x00  ",
            From="+15555551234",
        )
        assert payload.CallSid == "CA123"

    def test_phone_numbers_normalized(self) -> None:
        """Test that phone numbers are normalized."""
        payload = TwilioIncomingCallPayload(
            CallSid="CA123",
            From="1 (555) 555-1234",
            To="+1 555 555 5678",
        )
        assert payload.From == "+15555551234"
        assert payload.To == "+15555555678"

    def test_call_sid_too_long(self) -> None:
        """Test that CallSid exceeding max length is rejected."""
        with pytest.raises(ValidationError):
            TwilioIncomingCallPayload(
                CallSid="x" * 100,
                From="+15555551234",
            )

    def test_invalid_phone_rejected(self) -> None:
        """Test that invalid phone number is rejected."""
        with pytest.raises(ValidationError):
            TwilioIncomingCallPayload(
                CallSid="CA123",
                From="invalid",
            )


class TestTwilioVoicePayload:
    """Test TwilioVoicePayload validation."""

    def test_valid_payload_with_speech(self) -> None:
        """Test valid payload with speech result."""
        payload = TwilioVoicePayload(
            CallSid="CA123",
            SpeechResult="I want to make a reservation",
            Confidence=0.95,
        )
        assert payload.SpeechResult == "I want to make a reservation"
        assert payload.Confidence == 0.95

    def test_valid_payload_with_digits(self) -> None:
        """Test valid payload with DTMF digits."""
        payload = TwilioVoicePayload(
            CallSid="CA123",
            Digits="1234",
        )
        assert payload.Digits == "1234"

    def test_speech_result_sanitized(self) -> None:
        """Test that speech result is sanitized."""
        payload = TwilioVoicePayload(
            CallSid="CA123",
            SpeechResult="  hello\x00world  ",
        )
        assert payload.SpeechResult == "helloworld"

    def test_speech_result_too_long_rejected(self) -> None:
        """Test that speech result exceeding max length is rejected."""
        with pytest.raises(ValidationError):
            TwilioVoicePayload(
                CallSid="CA123",
                SpeechResult="x" * 5000,
            )

    def test_digits_must_be_numeric(self) -> None:
        """Test that Digits field must contain only numbers."""
        with pytest.raises(ValidationError, match="must be numeric"):
            TwilioVoicePayload(
                CallSid="CA123",
                Digits="123abc",
            )

    def test_digits_sanitized(self) -> None:
        """Test that Digits field is sanitized."""
        payload = TwilioVoicePayload(
            CallSid="CA123",
            Digits="  123  ",
        )
        assert payload.Digits == "123"

    def test_optional_fields_can_be_none(self) -> None:
        """Test that optional fields can be None."""
        payload = TwilioVoicePayload(
            CallSid="CA123",
            From=None,
            To=None,
            SpeechResult=None,
            Digits=None,
            Confidence=None,
        )
        assert payload.From is None
        assert payload.SpeechResult is None


class TestTwilioCallStatusPayload:
    """Test TwilioCallStatusPayload validation."""

    def test_valid_payload(self) -> None:
        """Test valid call status payload."""
        payload = TwilioCallStatusPayload(
            CallSid="CA123",
            CallStatus="completed",
        )
        assert payload.CallSid == "CA123"
        assert payload.CallStatus == "completed"

    def test_call_status_sanitized(self) -> None:
        """Test that CallStatus is sanitized."""
        payload = TwilioCallStatusPayload(
            CallSid="CA123",
            CallStatus="  in-progress\x00  ",
        )
        assert payload.CallStatus == "in-progress"

    def test_call_status_too_long_rejected(self) -> None:
        """Test that CallStatus exceeding max length is rejected."""
        with pytest.raises(ValidationError):
            TwilioCallStatusPayload(
                CallSid="CA123",
                CallStatus="x" * 100,
            )

    def test_missing_required_field(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            TwilioCallStatusPayload(CallSid="CA123")


class TestEndpointValidation:
    """
    Integration tests verifying endpoints properly validate with Pydantic.

    These tests ensure no raw request data reaches business logic without validation.
    """

    def test_twilio_incoming_rejects_missing_call_sid(self) -> None:
        """Test that missing CallSid returns 422."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        # Mock auth to bypass signature check
        from unittest.mock import patch

        from app.core.config import settings

        with patch.object(settings, "twilio_auth_token", None):
            response = client.post(
                "/twilio/incoming",
                data={
                    "From": "+15555551234",
                    # Missing CallSid
                },
            )

        assert response.status_code == 422

    def test_twilio_voice_rejects_invalid_data(self) -> None:
        """Test that invalid voice data returns 422."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        from unittest.mock import patch

        from app.core.config import settings

        with patch.object(settings, "twilio_auth_token", None):
            response = client.post(
                "/twilio/voice",
                data={
                    "CallSid": "x" * 100,  # Too long
                    "SpeechResult": "test",
                },
            )

        assert response.status_code == 422
