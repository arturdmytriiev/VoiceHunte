from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal

import structlog
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent import CallState, Intent, run_agent
from app.core.config import settings
from app.core.logging import call_id_ctx, configure_logging, request_id_ctx
from app.stt.whisper import SUPPORTED_LANGUAGES, transcribe

configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)

app = FastAPI(title=settings.app_name)

LanguageCode = Literal["sk", "en", "ru", "uk"]


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: LanguageCode
    call_id: str | None = None


class MVPResponse(BaseModel):
    transcript: str
    intent: Intent | None = None
    actions: list[str] = Field(default_factory=list)
    answer_text: str = ""
    reservation_id: int | None = None


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


def _extract_reservation_id(state: CallState) -> int | None:
    for result in state.tool_results:
        reservation_id = result.payload.get("reservation_id")
        if reservation_id is not None:
            return int(reservation_id)
    return None


def _build_response(state: CallState, transcript: str) -> MVPResponse:
    return MVPResponse(
        transcript=transcript,
        intent=state.intent,
        actions=state.final_answer.actions if state.final_answer else [],
        answer_text=state.final_answer.answer_text if state.final_answer else "",
        reservation_id=_extract_reservation_id(state),
    )


@app.post("/mvp/audio", response_model=MVPResponse)
async def mvp_audio(
    file: UploadFile = File(...),
    language: LanguageCode = "en",
    call_id: str | None = None,
) -> MVPResponse:
    if language not in SUPPORTED_LANGUAGES:
        return JSONResponse(
            status_code=422,
            content={"detail": "Unsupported language"},
        )

    suffix = Path(file.filename or "audio").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        temp_path = tmp_file.name

    try:
        stt_result = transcribe(temp_path, language=language, mode="transcribe")
    finally:
        os.unlink(temp_path)

    resolved_call_id = call_id or call_id_ctx.get() or str(uuid.uuid4())
    call_state = CallState(
        call_id=resolved_call_id,
        language=stt_result.language or language,
        last_user_text=stt_result.text,
    )
    call_state = run_agent(call_state)
    return _build_response(call_state, stt_result.text)


@app.post("/mvp/text", response_model=MVPResponse)
async def mvp_text(payload: TextRequest) -> MVPResponse:
    resolved_call_id = payload.call_id or call_id_ctx.get() or str(uuid.uuid4())
    call_state = CallState(
        call_id=resolved_call_id,
        language=payload.language,
        last_user_text=payload.text,
    )
    call_state = run_agent(call_state)
    return _build_response(call_state, payload.text)


@app.on_event("startup")
async def startup() -> None:
    logging.getLogger(__name__).info("service_started")
