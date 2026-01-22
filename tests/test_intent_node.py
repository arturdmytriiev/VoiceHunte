from __future__ import annotations

from app.agent.models import Intent
from app.agent.nodes.intent import classify_intent_and_entities


def test_intent_node_extracts_create_reservation() -> None:
    text = "I want to book a table for 2 on 2025-05-10 18:30, my name is Alice."
    extraction = classify_intent_and_entities(text)

    assert extraction.intent == Intent.create_reservation
    assert extraction.entities is not None
    assert extraction.entities.people == 2
    assert extraction.entities.name == "Alice"


def test_intent_node_extracts_cancel_reservation() -> None:
    text = "Please cancel reservation #123."
    extraction = classify_intent_and_entities(text)

    assert extraction.intent == Intent.cancel_reservation
    assert extraction.entities is not None
    assert extraction.entities.reservation_id == 123


def test_intent_node_extracts_menu_question() -> None:
    text = "Can I see the menu?"
    extraction = classify_intent_and_entities(text)

    assert extraction.intent == Intent.menu_question
