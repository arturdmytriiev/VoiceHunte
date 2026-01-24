from __future__ import annotations

import json
import sys
from unittest.mock import patch, MagicMock

# Mock heavy dependencies that aren't needed for unit tests
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["qdrant_client"] = MagicMock()

from app.agent.models import Intent
from app.agent.nodes.intent import (
    _llm_classify,
    _regex_fallback_extract,
    classify_intent_and_entities,
)


def test_regex_fallback_extracts_create_reservation() -> None:
    """Test regex fallback for create reservation intent."""
    text = "I want to book a table for 2 on 2025-05-10 18:30, my name is Alice."
    extraction = _regex_fallback_extract(text, None)

    assert extraction.intent == Intent.create_reservation
    assert extraction.entities is not None
    assert extraction.entities.people == 2
    assert extraction.entities.name == "Alice"


def test_regex_fallback_extracts_cancel_reservation() -> None:
    """Test regex fallback for cancel reservation intent."""
    text = "Please cancel my booking #123."
    extraction = _regex_fallback_extract(text, None)

    assert extraction.intent == Intent.cancel_reservation
    assert extraction.entities is not None
    assert extraction.entities.reservation_id == 123


def test_regex_fallback_extracts_menu_question() -> None:
    """Test regex fallback for menu question intent."""
    text = "Can I see the menu?"
    extraction = _regex_fallback_extract(text, None)

    assert extraction.intent == Intent.menu_question


def test_intent_node_extracts_create_reservation() -> None:
    """Test classify function with LLM disabled uses regex fallback."""
    text = "I want to book a table for 2 on 2025-05-10 18:30, my name is Alice."
    extraction = classify_intent_and_entities(text, use_llm_fallback=False)

    assert extraction.intent == Intent.create_reservation
    assert extraction.entities is not None
    assert extraction.entities.people == 2
    assert extraction.entities.name == "Alice"


def test_intent_node_extracts_cancel_reservation() -> None:
    """Test classify function with LLM disabled for cancel intent."""
    text = "Please cancel my booking #123."
    extraction = classify_intent_and_entities(text, use_llm_fallback=False)

    assert extraction.intent == Intent.cancel_reservation
    assert extraction.entities is not None
    assert extraction.entities.reservation_id == 123


def test_intent_node_extracts_menu_question() -> None:
    """Test classify function with LLM disabled for menu question."""
    text = "Can I see the menu?"
    extraction = classify_intent_and_entities(text, use_llm_fallback=False)

    assert extraction.intent == Intent.menu_question


def test_llm_classification_with_mock() -> None:
    """Test LLM classification with a mocked response."""
    mock_response = json.dumps({
        "intent": "create_reservation",
        "entities": {
            "name": "John",
            "datetime": "2025-06-15T19:00:00",
            "people": 4,
            "reservation_id": None,
        },
        "language": "en",
    })

    with patch("app.llm.openai_chat.chat_completion", return_value=mock_response):
        extraction = _llm_classify("Book a table for 4 people", None)

    assert extraction.intent == Intent.create_reservation
    assert extraction.entities is not None
    assert extraction.entities.name == "John"
    assert extraction.entities.people == 4
    assert extraction.language == "en"


def test_llm_classification_with_code_block() -> None:
    """Test LLM classification handles markdown code blocks in response."""
    mock_response = """```json
{
    "intent": "menu_question",
    "entities": null,
    "language": "en"
}
```"""

    with patch("app.llm.openai_chat.chat_completion", return_value=mock_response):
        extraction = _llm_classify("What dishes do you have?", None)

    assert extraction.intent == Intent.menu_question
    assert extraction.entities is None
    assert extraction.language == "en"


def test_classify_uses_custom_llm_when_provided() -> None:
    """Test that custom LLM callable is used when provided."""
    mock_response = json.dumps({
        "intent": "hours_info",
        "entities": None,
        "language": "en",
    })

    def custom_llm(prompt: str) -> str:
        return mock_response

    extraction = classify_intent_and_entities(
        "What are your opening hours?",
        llm=custom_llm,
    )

    assert extraction.intent == Intent.hours_info
    assert extraction.language == "en"


def test_classify_falls_back_to_regex_on_invalid_llm_response() -> None:
    """Test fallback to regex when LLM returns invalid JSON."""
    def bad_llm(prompt: str) -> str:
        return "This is not valid JSON"

    extraction = classify_intent_and_entities(
        "I want to book a table",
        llm=bad_llm,
    )

    assert extraction.intent == Intent.create_reservation
