from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import structlog
from fastapi import Request
from fastapi.responses import Response
from pydantic import ValidationError

from app.agent import CallState, run_agent
from app.db.conversations import ConversationStore
from app.tts import tts_to_file
from app.twilio.models import (
    TwilioCallStatusPayload,
    TwilioIncomingCallPayload,
    TwilioVoicePayload,
)
from app.twilio.security import verify_twilio_signature
from app.twilio.twiml import (
    create_twiml_response,
    get_polly_voice,
    get_twilio_language,
)

logger = structlog.get_logger(__name__)

store = ConversationStore()


def _serialize_tool_calls(state: CallState) -> list[dict]:
    return [result.model_dump() for result in state.tool_results]


async def handle_incoming_call(request: Request) -> Response:
    """
    Handle incoming Twilio call.
    This is the initial webhook when a call is received.
    """
    form_data = await request.form()
    if not verify_twilio_signature(request, form_data):
        return Response(status_code=403)

    try:
        payload = TwilioIncomingCallPayload.model_validate(form_data)
    except ValidationError:
        return Response(status_code=422)
    call_sid = payload.CallSid
    from_number = payload.From
    to_number = payload.To

    logger.info(
        "incoming_call",
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
    )

    # Default to English, will be detected from speech
    language = "en"

    twiml = create_twiml_response(
        gather={
            "input": "speech",
            "action": "/twilio/voice",
            "method": "POST",
            "language": get_twilio_language(language),
            "speech_timeout": "auto",
            "say": "Hello! Welcome to our restaurant. How can I help you today?",
            "voice": get_polly_voice(language),
        }
    )

    return Response(content=twiml, media_type="application/xml")


async def handle_voice_input(
    request: Request,
) -> Response:
    """
    Handle voice input from Twilio.
    This receives the transcribed speech from the user.
    """
    form_data = await request.form()
    if not verify_twilio_signature(request, form_data):
        twiml = create_twiml_response(say="We could not verify this request.")
        return Response(
            content=twiml,
            media_type="application/xml",
            status_code=403,
        )

    try:
        payload = TwilioVoicePayload.model_validate(form_data)
    except ValidationError:
        return Response(status_code=422)

    logger.info(
        "voice_input",
        call_sid=payload.CallSid,
        speech_result=payload.SpeechResult,
        confidence=payload.Confidence,
    )

    if not payload.SpeechResult:
        twiml = create_twiml_response(
            gather={
                "input": "speech",
                "action": "/twilio/voice",
                "method": "POST",
                "language": get_twilio_language("en"),
                "speech_timeout": "auto",
                "say": "I didn't catch that. Could you please repeat?",
            }
        )
        return Response(content=twiml, media_type="application/xml")

    # Process through agent
    call_state = CallState(
        call_id=payload.CallSid,
        language="en",  # Will be detected by agent
        last_user_text=payload.SpeechResult,
    )
    call_state = run_agent(call_state)

    # Get turn ID
    turn_id = store.next_turn_id(payload.CallSid)

    # Store in database
    store.create_turn(
        call_id=payload.CallSid,
        language=call_state.language,
        user_text=payload.SpeechResult,
        intent=call_state.intent.value if call_state.intent else None,
        tool_calls=_serialize_tool_calls(call_state),
        assistant_text=call_state.final_answer.answer_text
        if call_state.final_answer
        else None,
        turn_id=turn_id,
    )

    # Generate response
    answer_text = (
        call_state.final_answer.answer_text
        if call_state.final_answer
        else "I'm sorry, I couldn't process your request."
    )

    detected_language = call_state.language or "en"
    twilio_language = get_twilio_language(detected_language)

    # Check if we need more clarification
    needs_clarification = (
        call_state.final_answer
        and "clarify" in call_state.final_answer.actions
    )

    if needs_clarification:
        tts_text = answer_text
    else:
        tts_text = f"{answer_text}. Thank you for calling. Goodbye!"

    tts_dir = Path("storage/tts") / payload.CallSid
    tts_dir.mkdir(parents=True, exist_ok=True)
    tts_filename = f"turn_{turn_id}.mp3"
    tts_path = tts_dir / tts_filename
    tts_to_file(tts_text, str(tts_path))
    base_url = str(request.base_url).rstrip("/")
    tts_url = f"{base_url}/twilio/tts/{payload.CallSid}/{tts_filename}"

    if needs_clarification:
        # Continue conversation with gather
        twiml = create_twiml_response(
            gather={
                "input": "speech",
                "action": "/twilio/voice",
                "method": "POST",
                "language": twilio_language,
                "speech_timeout": "auto",
                "play": tts_url,
                "voice": get_polly_voice(detected_language),
            }
        )
    else:
        # Final response and hangup
        twiml = create_twiml_response(
            play=tts_url,
            hangup=True,
        )

    return Response(content=twiml, media_type="application/xml")


async def handle_call_status(request: Request) -> Response:
    """
    Handle call status updates from Twilio.
    """
    form_data = await request.form()
    if not verify_twilio_signature(request, form_data):
        return Response(status_code=403)

    try:
        payload = TwilioCallStatusPayload.model_validate(form_data)
    except ValidationError:
        return Response(status_code=422)
    call_sid = payload.CallSid
    call_status = payload.CallStatus

    logger.info(
        "call_status_update",
        call_sid=call_sid,
        status=call_status,
    )

    return Response(content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")
