from __future__ import annotations

from typing import Callable

from app.agent.models import Intent
from app.agent.nodes.intent import classify_intent_and_entities
from app.agent.nodes.respond import respond
from app.agent.nodes.tools_crm import handle_crm_tools
from app.agent.nodes.tools_menu import handle_menu_tools
from app.agent.state import CallState


def _ensure_history(state: CallState) -> None:
    if state.last_user_text and not any(
        msg.text == state.last_user_text and msg.role == "user"
        for msg in state.history
    ):
        state.add_history("user", state.last_user_text)


def run_agent(
    call_state: CallState,
    llm: Callable[[str], str] | None = None,
    max_turns: int = 2,
) -> CallState:
    _ensure_history(call_state)

    user_messages = [msg for msg in call_state.history if msg.role == "user"]
    if not user_messages:
        return call_state

    turns = 0
    start_index = max(0, len(user_messages) - max_turns)
    for message in user_messages[start_index:]:
        turns += 1
        call_state.last_user_text = message.text
        extraction = classify_intent_and_entities(
            message.text, call_state.language, llm
        )
        call_state.intent = extraction.intent
        call_state.entities = extraction.entities
        call_state.language = extraction.language
        call_state.tool_results = []

        if call_state.intent in {
            Intent.create_reservation,
            Intent.update_reservation,
            Intent.cancel_reservation,
        }:
            call_state = handle_crm_tools(call_state)
        elif call_state.intent == Intent.menu_question:
            call_state = handle_menu_tools(call_state)

        call_state = respond(call_state)
        call_state.add_history("assistant", call_state.final_answer.answer_text)

        if "clarify" not in call_state.final_answer.actions:
            break

    return call_state
