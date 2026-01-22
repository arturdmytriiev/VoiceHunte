from __future__ import annotations

import structlog
from fastapi import Request
from starlette.datastructures import FormData
from twilio.request_validator import RequestValidator

from app.core.config import settings

logger = structlog.get_logger(__name__)


def build_twilio_request_url(request: Request) -> str:
    headers = request.headers
    proto = headers.get("x-forwarded-proto", request.url.scheme)
    host = headers.get("x-forwarded-host", headers.get("host", request.url.netloc))
    host = host or request.url.netloc
    path = request.url.path
    query = request.url.query
    url = f"{proto}://{host}{path}"
    if query:
        url = f"{url}?{query}"
    return url


def extract_form_params(form_data: FormData) -> dict[str, str]:
    return {key: value for key, value in form_data.multi_items()}


def validate_twilio_signature(
    *,
    auth_token: str,
    signature: str,
    url: str,
    params: dict[str, str],
) -> bool:
    validator = RequestValidator(auth_token)
    return validator.validate(url, params, signature)


def verify_twilio_signature(request: Request, form_data: FormData) -> bool:
    signature = request.headers.get("x-twilio-signature")
    if not signature:
        logger.warning("twilio_signature_missing")
        return False

    auth_token = settings.twilio_auth_token
    if not auth_token:
        logger.warning("twilio_auth_token_missing")
        return False

    url = build_twilio_request_url(request)
    params = extract_form_params(form_data)
    return validate_twilio_signature(
        auth_token=auth_token,
        signature=signature,
        url=url,
        params=params,
    )
