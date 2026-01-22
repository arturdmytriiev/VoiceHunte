from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_text(value: str, max_length: int) -> str:
    cleaned = CONTROL_CHARS_RE.sub("", value.strip())
    if not cleaned:
        raise ValueError("Value must not be empty")
    if len(cleaned) > max_length:
        raise ValueError("Value is too long")
    return cleaned


def _sanitize_optional_text(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    return _sanitize_text(value, max_length)


def _normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = CONTROL_CHARS_RE.sub("", value.strip())
    cleaned = re.sub(r"[()\s\-\.]", "", cleaned)
    if cleaned.startswith("+"):
        digits = cleaned[1:]
    else:
        digits = cleaned
    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        raise ValueError("Invalid phone number")
    return f"+{digits}"


class TwilioIncomingCallPayload(BaseModel):
    CallSid: str = Field(..., min_length=1, max_length=64)
    From: str | None = None
    To: str | None = None

    @field_validator("CallSid")
    @classmethod
    def validate_call_sid(cls, value: str) -> str:
        return _sanitize_text(value, 64)

    @field_validator("From", "To")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _normalize_phone(value)


class TwilioVoicePayload(BaseModel):
    CallSid: str = Field(..., min_length=1, max_length=64)
    From: str | None = None
    To: str | None = None
    SpeechResult: str | None = None
    Digits: str | None = None
    Confidence: float | None = None

    @field_validator("CallSid")
    @classmethod
    def validate_call_sid(cls, value: str) -> str:
        return _sanitize_text(value, 64)

    @field_validator("From", "To")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _normalize_phone(value)

    @field_validator("SpeechResult")
    @classmethod
    def validate_speech_result(cls, value: str | None) -> str | None:
        return _sanitize_optional_text(value, 4000)

    @field_validator("Digits")
    @classmethod
    def validate_digits(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _sanitize_text(value, 32)
        if not cleaned.isdigit():
            raise ValueError("Digits must be numeric")
        return cleaned


class TwilioCallStatusPayload(BaseModel):
    CallSid: str = Field(..., min_length=1, max_length=64)
    CallStatus: str = Field(..., min_length=1, max_length=32)

    @field_validator("CallSid")
    @classmethod
    def validate_call_sid(cls, value: str) -> str:
        return _sanitize_text(value, 64)

    @field_validator("CallStatus")
    @classmethod
    def validate_call_status(cls, value: str) -> str:
        return _sanitize_text(value, 32)


class TwilioRecordingStatusPayload(BaseModel):
    CallSid: str = Field(..., min_length=1, max_length=64)
    RecordingSid: str = Field(..., min_length=1, max_length=64)
    RecordingUrl: str = Field(..., min_length=1, max_length=512)
    RecordingStatus: str = Field(..., min_length=1, max_length=32)
    From: str | None = None
    To: str | None = None

    @field_validator("CallSid", "RecordingSid")
    @classmethod
    def validate_sid(cls, value: str) -> str:
        return _sanitize_text(value, 64)

    @field_validator("RecordingUrl")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _sanitize_text(value, 512)

    @field_validator("RecordingStatus")
    @classmethod
    def validate_status(cls, value: str) -> str:
        return _sanitize_text(value, 32)

    @field_validator("From", "To")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _normalize_phone(value)


def sanitize_text_payload(value: str, max_length: int = 4000) -> str:
    return _sanitize_text(value, max_length)


def sanitize_optional_payload(value: str | None, max_length: int = 4000) -> str | None:
    return _sanitize_optional_text(value, max_length)


def normalize_phone_payload(value: str | None) -> str | None:
    return _normalize_phone(value)
