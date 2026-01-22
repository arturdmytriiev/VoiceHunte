from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import structlog
from fastapi import Form, Request
from fastapi.responses import Response

from app.agent import CallState, run_agent
from app.db.conversations import ConversationStore
from app.tts import tts_to_file
from app.twilio.twiml import create_twiml_response, get_polly_voice

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
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")

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
            "language": "en-US",
            "speech_timeout": "auto",
            "say": "Hello! Welcome to our restaurant. How can I help you today?",
            "voice": get_polly_voice(language),
        }
    )

    return Response(content=twiml, media_type="application/xml")


async def handle_voice_input(
    request: Request,
    SpeechResult: str = Form(None),
    CallSid: str = Form(...),
    Confidence: float = Form(None),
) -> Response:
    """
    Handle voice input from Twilio.
    This receives the transcribed speech from the user.
    """
    logger.info(
        "voice_input",
        call_sid=CallSid,
        speech_result=SpeechResult,
        confidence=Confidence,
    )

    if not SpeechResult:
        twiml = create_twiml_response(
            gather={
                "input": "speech",
                "action": "/twilio/voice",
                "method": "POST",
                "language": "en-US",
                "speech_timeout": "auto",
                "say": "I didn't catch that. Could you please repeat?",
            }
        )
        return Response(content=twiml, media_type="application/xml")

    # Process through agent
    call_state = CallState(
        call_id=CallSid,
        language="en",  # Will be detected by agent
        last_user_text=SpeechResult,
    )
    call_state = run_agent(call_state)

    # Get turn ID
    turn_id = store.next_turn_id(CallSid)

    # Store in database
    store.create_turn(
        call_id=CallSid,
        language=call_state.language,
        user_text=SpeechResult,
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

    # Check if we need more clarification
    needs_clarification = (
        call_state.final_answer
        and "clarify" in call_state.final_answer.actions
    )

    if needs_clarification:
        # Continue conversation with gather
        twiml = create_twiml_response(
            gather={
                "input": "speech",
                "action": "/twilio/voice",
                "method": "POST",
                "language": f"{detected_language}-US" if detected_language == "en" else detected_language,
                "speech_timeout": "auto",
                "say": answer_text,
                "voice": get_polly_voice(detected_language),
            }
        )
    else:
        # Final response and hangup
        twiml = create_twiml_response(
            say=f"{answer_text}. Thank you for calling. Goodbye!",
            hangup=True,
        )

    return Response(content=twiml, media_type="application/xml")


async def handle_call_status(request: Request) -> Response:
    """
    Handle call status updates from Twilio.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")

    logger.info(
        "call_status_update",
        call_sid=call_sid,
        status=call_status,
    )

    return Response(content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")
