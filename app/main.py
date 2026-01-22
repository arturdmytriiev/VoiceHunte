from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs

import anyio
import requests
import structlog
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.agent import CallState, Intent, run_agent
from app.core.config import settings
from app.core.errors import ExternalAPIError
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
from app.twilio.twiml import create_twiml_response

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
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
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


def _twilio_rate_key(request: Request) -> str:
    from_number = getattr(request.state, "twilio_from", None)
    if from_number:
        return f"twilio:{from_number}"
    return get_remote_address(request)


def _is_twilio_request(request: Request) -> bool:
    return request.url.path.startswith("/twilio/")


def _twilio_error_response(message: str, status_code: int = 200) -> Response:
    twiml = create_twiml_response(say=message)
    return Response(content=twiml, media_type="application/xml", status_code=status_code)


@app.middleware("http")
async def capture_twilio_fields(request: Request, call_next):
    if request.url.path.startswith("/twilio/") and request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/x-www-form-urlencoded"):
            body = await request.body()
            parsed = parse_qs(body.decode("utf-8"))
            request.state.twilio_from = parsed.get("From", [None])[0]
            request.state.twilio_call_sid = parsed.get("CallSid", [None])[0]

            async def receive() -> dict[str, object]:
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive  # type: ignore[attr-defined]

    return await call_next(request)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    call_id = (
        request.headers.get("x-call-id")
        or getattr(request.state, "twilio_call_sid", None)
        or str(uuid.uuid4())
    )

    request_id_token = request_id_ctx.set(request_id)
    call_id_token = call_id_ctx.set(call_id)

    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(request_id_token)
        call_id_ctx.reset(call_id_token)

    response.headers["x-request-id"] = request_id
    response.headers["x-call-id"] = call_id
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    logger.warning("request_validation_failed", path=request.url.path, error=str(exc))
    if _is_twilio_request(request):
        return _twilio_error_response("Извините, произошла ошибка. Попробуйте позже.")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    logger.warning("pydantic_validation_failed", path=request.url.path, error=str(exc))
    if _is_twilio_request(request):
        return _twilio_error_response("Извините, произошла ошибка. Попробуйте позже.")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(ExternalAPIError)
async def external_api_handler(request: Request, exc: ExternalAPIError):
    logger.warning(
        "external_api_failed",
        path=request.url.path,
        service=exc.service,
        status_code=exc.status_code,
    )
    if _is_twilio_request(request):
        return _twilio_error_response("Извините, произошла ошибка. Попробуйте позже.")
    return JSONResponse(
        status_code=503,
        content={"detail": f"Upstream {exc.service} error"},
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("rate_limit_exceeded", path=request.url.path)
    if _is_twilio_request(request):
        return _twilio_error_response(
            "Слишком много запросов. Попробуйте позже.", status_code=429
        )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please slow down."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception", path=request.url.path)
    if _is_twilio_request(request):
        return _twilio_error_response("Извините, произошла ошибка. Попробуйте позже.")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


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
@limiter.limit(settings.admin_rate_limit)
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
@limiter.limit(settings.admin_rate_limit)
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
@limiter.limit(settings.admin_rate_limit)
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
@limiter.limit(settings.twilio_rate_limit, key_func=_twilio_rate_key)
async def twilio_incoming(request: Request) -> Response:
    """
    Twilio webhook for incoming calls.
    """
    return await handle_incoming_call(request)


@app.post("/twilio/voice")
@limiter.limit(settings.twilio_rate_limit, key_func=_twilio_rate_key)
async def twilio_voice(request: Request) -> Response:
    """
    Twilio webhook for voice input processing.
    """
    return await handle_voice_input(request)


@app.post("/twilio/status")
@limiter.limit(settings.twilio_rate_limit, key_func=_twilio_rate_key)
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
