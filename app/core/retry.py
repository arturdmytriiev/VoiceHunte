from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.core.config import settings
from app.core.errors import ExternalAPIError

logger = structlog.get_logger(__name__)


def _is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, ExternalAPIError):
        if exc.status_code is None:
            return True
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _log_retry(service: str) -> Callable[[Any], None]:
    def _log(state: Any) -> None:
        outcome = state.outcome
        reason = None
        if outcome and outcome.failed:
            reason = str(outcome.exception())
        logger.warning(
            "external_api_retry",
            service=service,
            attempt=state.attempt_number,
            reason=reason,
        )

    return _log


def retryable(service: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    return retry(
        retry=retry_if_exception(_is_retryable_exception),
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential_jitter(
            initial=settings.retry_backoff_initial,
            max=settings.retry_backoff_max,
        ),
        before_sleep=_log_retry(service),
        reraise=True,
    )


def raise_for_retryable_status(response: requests.Response, service: str) -> None:
    if response.status_code == 429 or response.status_code >= 500:
        raise ExternalAPIError(
            service,
            f"{service} error {response.status_code}: {response.text}",
            status_code=response.status_code,
        )
    response.raise_for_status()
