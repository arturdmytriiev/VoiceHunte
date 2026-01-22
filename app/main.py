from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import anyio
import requests
import structlog
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agent import CallState, Intent, run_agent
from app.core.config import settings
from app.core.logging import call_id_ctx, configure_logging, request_id_ctx
from app.db.conversations import ConversationStore
from app.db.pool import close_pool, get_pool, init_pool
from app.stt.whisper import SUPPORTED_LANGUAGES, transcribe
from app.tts import stream_tts
from app.twilio.models import sanitize_optional_payload, sanitize_text_payload
from app.twilio.webhooks import (
    handle_call_status,
    handle_incoming_call,
    handle_voice_input,
)

configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
store = ConversationStore()

LanguageCode = Literal["sk", "en", "ru", "uk"]


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: LanguageCode
    call_id: str | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return sanitize_text_payload(value, max_length=4000)

    @field_validator("call_id")
    @classmethod
    def validate_call_id(cls, value: str | None) -> str | None:
        return sanitize_optional_payload(value, max_length=128)


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


def _serialize_tool_calls(state: CallState) -> list[dict[str, object]]:
    return [result.model_dump() for result in state.tool_results]


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

    resolved_call_id = call_id or call_id_ctx.get() or str(uuid.uuid4())
    turn_id = store.next_turn_id(resolved_call_id)
    audio_dir = Path("storage/audio") / resolved_call_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"input_{turn_id}.wav"

    suffix = Path(file.filename or "audio").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        temp_path = tmp_file.name
    shutil.copy(temp_path, audio_path)

    try:
        stt_result = transcribe(temp_path, language=language, mode="transcribe")
    finally:
        os.unlink(temp_path)

    call_state = CallState(
        call_id=resolved_call_id,
        language=stt_result.language or language,
        last_user_text=stt_result.text,
    )
    call_state = run_agent(call_state)

    store.create_turn(
        call_id=resolved_call_id,
        language=call_state.language,
        user_text=stt_result.text,
        intent=call_state.intent.value if call_state.intent else None,
        tool_calls=_serialize_tool_calls(call_state),
        assistant_text=call_state.final_answer.answer_text
        if call_state.final_answer
        else None,
        turn_id=turn_id,
    )
    store.record_audio(
        call_id=resolved_call_id,
        turn_id=turn_id,
        path=str(audio_path),
        kind="input",
    )
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
    store.create_turn(
        call_id=resolved_call_id,
        language=call_state.language,
        user_text=payload.text,
        intent=call_state.intent.value if call_state.intent else None,
        tool_calls=_serialize_tool_calls(call_state),
        assistant_text=call_state.final_answer.answer_text
        if call_state.final_answer
        else None,
    )
    return _build_response(call_state, payload.text)


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str = "alloy"
    model: str = "tts-1"
    response_format: str = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return sanitize_text_payload(value, max_length=4000)


@app.post("/tts/stream")
async def tts_stream(payload: TTSRequest) -> StreamingResponse:
    """
    Stream TTS audio from OpenAI.
    Returns audio in chunks for streaming playback.
    """
    try:
        audio_stream = stream_tts(
            payload.text,
            voice=payload.voice,
            model=payload.model,
            response_format=payload.response_format,
            speed=payload.speed,
        )

        media_type_map = {
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "aac": "audio/aac",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "pcm": "audio/pcm",
        }
        media_type = media_type_map.get(payload.response_format, "audio/mpeg")

        return StreamingResponse(audio_stream, media_type=media_type)
    except Exception as e:
        logger.exception("tts_stream_failed", error=str(e))
        return JSONResponse(
            status_code=500,
            content={"detail": f"TTS generation failed: {str(e)}"},
        )


@app.post("/twilio/incoming")
async def twilio_incoming(request: Request) -> Response:
    """
    Twilio webhook for incoming calls.
    """
    return await handle_incoming_call(request)


@app.post("/twilio/voice")
async def twilio_voice(request: Request) -> Response:
    """
    Twilio webhook for voice input processing.
    """
    return await handle_voice_input(request)


@app.post("/twilio/status")
async def twilio_status(request: Request) -> Response:
    """
    Twilio webhook for call status updates.
    """
    return await handle_call_status(request)


@app.get("/twilio/tts/{call_id}/{filename}")
async def twilio_tts(call_id: str, filename: str) -> Response:
    """
    Serve generated TTS audio for Twilio <Play>.
    """
    tts_path = Path("storage/tts") / call_id / filename
    if not tts_path.exists():
        raise HTTPException(status_code=404, detail="TTS file not found")
    return FileResponse(tts_path, media_type="audio/mpeg")


@app.get("/ready")
async def ready() -> JSONResponse:
    checks: dict[str, dict[str, str]] = {}
    status_code = 200

    def set_failure(name: str, error: Exception) -> None:
        nonlocal status_code
        checks[name] = {"status": "error", "error": str(error)}
        status_code = 503

    async def run_check(name: str, func) -> None:
        try:
            async with anyio.fail_after(1.5):
                await anyio.to_thread.run_sync(func)
            checks[name] = {"status": "ok"}
        except Exception as exc:  # noqa: BLE001 - narrow errors not needed for health
            set_failure(name, exc)

    def check_postgres() -> None:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

    def check_qdrant() -> None:
        url = f"{settings.qdrant_url.rstrip('/')}/collections"
        response = requests.get(url, timeout=1.5)
        response.raise_for_status()

    def check_openai() -> None:
        if not settings.openai_api_key:
            raise RuntimeError("openai_api_key missing")
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=1.5,
        )
        response.raise_for_status()

    await run_check("postgres", check_postgres)
    await run_check("qdrant", check_qdrant)
    await run_check("openai", check_openai)

    overall = "ok" if status_code == 200 else "error"
    return JSONResponse(status_code=status_code, content={"status": overall, "checks": checks})


@app.on_event("startup")
async def startup() -> None:
    logging.getLogger(__name__).info("service_started")
    if not settings.twilio_account_sid:
        logging.getLogger(__name__).warning("twilio_account_sid_missing")
    if not settings.twilio_auth_token:
        logging.getLogger(__name__).warning("twilio_auth_token_missing")
    if not settings.twilio_phone_number:
        logging.getLogger(__name__).warning("twilio_phone_number_missing")
