from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

import structlog

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
call_id_ctx: ContextVar[str | None] = ContextVar("call_id", default=None)


def _add_context_fields(_: logging.Logger, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict["request_id"] = request_id_ctx.get()
    event_dict["call_id"] = call_id_ctx.get()
    return event_dict


def _rename_event_to_message(_: logging.Logger, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _serialize_json(_: logging.Logger, __: str, event_dict: dict[str, Any]) -> str:
    return json.dumps(event_dict, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.add_log_level,
            _add_context_fields,
            _rename_event_to_message,
            structlog.processors.format_exc_info,
            _serialize_json,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.call_id = call_id_ctx.get()
        record.timestamp = datetime.now(timezone.utc).isoformat()
        return True
