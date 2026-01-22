from starlette.requests import Request
from twilio.request_validator import RequestValidator

from app.twilio.security import build_twilio_request_url, validate_twilio_signature


def _make_request(headers: dict[str, str], path: str = "/twilio/voice") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "scheme": "http",
        "server": ("internal", 80),
        "query_string": b"",
    }
    return Request(scope)


def test_build_twilio_request_url_respects_forwarded_headers() -> None:
    request = _make_request(
        {
            "x-forwarded-proto": "https",
            "x-forwarded-host": "example.com",
            "host": "internal",
        }
    )
    assert build_twilio_request_url(request) == "https://example.com/twilio/voice"


def test_validate_twilio_signature_valid() -> None:
    auth_token = "test_auth_token"
    url = "https://example.com/twilio/voice"
    params = {"CallSid": "CA123", "From": "+1234567890"}
    validator = RequestValidator(auth_token)
    signature = validator.compute_signature(url, params)
    assert validate_twilio_signature(
        auth_token=auth_token,
        signature=signature,
        url=url,
        params=params,
    )


def test_validate_twilio_signature_invalid() -> None:
    auth_token = "test_auth_token"
    url = "https://example.com/twilio/voice"
    params = {"CallSid": "CA123", "From": "+1234567890"}
    assert not validate_twilio_signature(
        auth_token=auth_token,
        signature="bad-signature",
        url=url,
        params=params,
    )
