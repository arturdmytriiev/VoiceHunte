from __future__ import annotations

import logging
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import call_id_ctx, configure_logging, request_id_ctx

configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)

app = FastAPI(title=settings.app_name)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    call_id = request.headers.get("x-call-id") or str(uuid.uuid4())

    request_id_token = request_id_ctx.set(request_id)
    call_id_token = call_id_ctx.set(call_id)

    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 - intentional to capture all errors
        logger.exception("request_failed", path=request.url.path)
        request_id_ctx.reset(request_id_token)
        call_id_ctx.reset(call_id_token)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    response.headers["x-request-id"] = request_id
    response.headers["x-call-id"] = call_id
    request_id_ctx.reset(request_id_token)
    call_id_ctx.reset(call_id_token)
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    logger.info("health_check")
    return {"status": "ok"}


@app.on_event("startup")
async def startup() -> None:
    logging.getLogger(__name__).info("service_started")
