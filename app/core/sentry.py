from __future__ import annotations

import re
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from app.core.config import settings

PHONE_PATTERN = re.compile(r"\+?\d[\d\-\(\)\s]{7,}\d")


def mask_pii(text: str | None) -> str | None:
    """Mask phone numbers and other PII from text."""
    if text is None:
        return None
    # Mask phone numbers
    text = PHONE_PATTERN.sub("[PHONE_REDACTED]", text)
    return text


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Filter and sanitize Sentry events before sending."""
    # Add correlation IDs as tags if available
    if "request" in hint:
        request = hint["request"]
        if hasattr(request, "headers"):
            call_sid = request.headers.get("x-call-id")
            request_id = request.headers.get("x-request-id")
            if call_sid:
                event.setdefault("tags", {})["call_sid"] = call_sid
            if request_id:
                event.setdefault("tags", {})["request_id"] = request_id

    # Mask PII in exception messages
    if "exception" in event:
        for exception in event["exception"].get("values", []):
            if "value" in exception:
                exception["value"] = mask_pii(exception["value"])

    # Mask PII in breadcrumbs
    if "breadcrumbs" in event:
        for breadcrumb in event["breadcrumbs"].get("values", []):
            if "message" in breadcrumb:
                breadcrumb["message"] = mask_pii(breadcrumb["message"])
            if "data" in breadcrumb:
                for key, value in breadcrumb["data"].items():
                    if isinstance(value, str):
                        breadcrumb["data"][key] = mask_pii(value)

    return event


def init_sentry() -> None:
    """Initialize Sentry error tracking with PII filtering."""
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(
                level=None,  # Capture all log levels
                event_level=None,  # Don't create events from logs
            ),
        ],
        traces_sample_rate=0.1,  # Sample 10% of transactions
        before_send=before_send,
        send_default_pii=False,  # Don't send PII by default
        attach_stacktrace=True,
        max_breadcrumbs=50,
    )

    # Set global tags
    sentry_sdk.set_tag("service", settings.app_name)
    sentry_sdk.set_tag("environment", settings.environment)
