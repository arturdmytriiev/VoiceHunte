from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Callable

import structlog
from pydantic import BaseModel, ValidationError

from app.agent.models import Intent, ReservationRequest
from app.core.config import settings

logger = structlog.get_logger(__name__)


class IntentExtraction(BaseModel):
    intent: Intent
    entities: ReservationRequest | None = None
    language: str


def build_intent_prompt(text: str, language: str | None) -> str:
    lang_hint = language or "auto"
    return (
        "You are an intent classifier for a restaurant call center. "
        "Return ONLY valid JSON that matches this schema: "
        "{\"intent\": \"create_reservation|update_reservation|cancel_reservation|menu_question|hours_info|generic\", "
        "\"entities\": {\"name\": string|null, \"datetime\": string|null, \"people\": number|null, \"reservation_id\": number|null}, "
        "\"language\": string}. "
        "Use ISO 8601 for datetime when possible. "
        f"Caller language hint: {lang_hint}. "
        f"User text: {text!r}"
    )


def detect_language(text: str) -> str:
    if re.search(r"[а-яА-ЯёЁ]", text):
        if re.search(r"[іїєґ]", text):
            return "uk"
        return "ru"
    if re.search(r"[áäčďéíľĺňóôŕšťúýž]", text, re.IGNORECASE):
        return "sk"
    return "en"


def _parse_datetime(text: str) -> datetime | None:
    iso_match = re.search(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", text)
    if iso_match:
        try:
            return datetime.fromisoformat(iso_match.group(0).replace(" ", "T"))
        except ValueError:
            return None
    date_match = re.search(r"(\d{2})[./](\d{2})[./](\d{4})", text)
    time_match = re.search(r"(\d{1,2}):(\d{2})", text)
    if date_match and time_match:
        day, month, year = date_match.groups()
        hour, minute = time_match.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
        except ValueError:
            return None
    return None


def _extract_people(text: str) -> int | None:
    match = re.search(
        r"(\d+)\s*(people|persons|guests|ppl|чел|человек|людей|os[ôo]b|osoby)",
        text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    standalone = re.search(r"\b(\d{1,2})\b", text)
    if standalone:
        return int(standalone.group(1))
    return None


def _extract_name(text: str) -> str | None:
    patterns = [
        r"my name is ([A-Za-zÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ\- ]+)",
        r"i am ([A-Za-zÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ\- ]+)",
        r"меня зовут ([А-Яа-яёЁ\- ]+)",
        r"я ([А-Яа-яёЁ\- ]+)",
        r"мене звати ([А-Яа-яёЁ\- ]+)",
        r"vol[aá]m sa ([A-Za-zÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ\- ]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_reservation_id(text: str) -> int | None:
    match = re.search(r"(?:id|#|брон|rezerv)\s*(\d{1,6})", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _fallback_intent(text: str) -> Intent:
    lowered = text.lower()
    # Check cancel first (before create) to handle "cancel booking/reservation"
    if re.search(r"(cancel|отмен|скас|zruš)", lowered):
        return Intent.cancel_reservation
    if re.search(r"(change|update|move|измен|перен|змін|zmeni|upravi)", lowered):
        return Intent.update_reservation
    if re.search(r"(book|reserve|reservation|заброн|брон|rezerv|rezer)", lowered):
        return Intent.create_reservation
    if re.search(r"(menu|меню|страв|jedlo|jedálny|ponuka)", lowered):
        return Intent.menu_question
    if re.search(r"(hours|open|close|работ|відкрит|otvár|hodin|час)", lowered):
        return Intent.hours_info
    return Intent.generic


def _regex_fallback_extract(text: str, language: str | None) -> IntentExtraction:
    """Extract intent and entities using regex patterns (ultimate fallback)."""
    detected_language = language or detect_language(text)
    entities = ReservationRequest(
        name=_extract_name(text),
        datetime=_parse_datetime(text),
        people=_extract_people(text),
        reservation_id=_extract_reservation_id(text),
    )
    if not any(
        [entities.name, entities.datetime, entities.people, entities.reservation_id]
    ):
        entities = None
    return IntentExtraction(
        intent=_fallback_intent(text),
        entities=entities,
        language=detected_language,
    )


def _llm_classify(text: str, language: str | None) -> IntentExtraction:
    """Classify intent using OpenAI LLM."""
    from app.llm.openai_chat import chat_completion

    prompt = build_intent_prompt(text, language)
    raw = chat_completion(prompt, temperature=0.0, max_tokens=256)

    try:
        raw_stripped = raw.strip()
        if raw_stripped.startswith("```"):
            lines = raw_stripped.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith("```") and not in_json:
                    in_json = True
                    continue
                if line.startswith("```") and in_json:
                    break
                if in_json:
                    json_lines.append(line)
            raw_stripped = "\n".join(json_lines)

        payload = json.loads(raw_stripped)
        return IntentExtraction.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(
            "llm_classification_parse_error",
            error=str(e),
            raw_response=raw[:500],
        )
        raise


def classify_intent_and_entities(
    text: str,
    language: str | None = None,
    llm: Callable[[str], str] | None = None,
    use_llm_fallback: bool = True,
) -> IntentExtraction:
    """
    Classify intent and extract entities from user text.

    Args:
        text: User input text
        language: Language hint (auto-detected if not provided)
        llm: Optional custom LLM callable (for testing or custom models)
        use_llm_fallback: If True, use OpenAI LLM when no custom llm is provided
                         and OPENAI_API_KEY is configured. Falls back to regex
                         if LLM fails or is not available.

    Returns:
        IntentExtraction with intent, entities, and language
    """
    if llm is not None:
        prompt = build_intent_prompt(text, language)
        raw = llm(prompt)
        try:
            payload = json.loads(raw)
            return IntentExtraction.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            logger.warning("custom_llm_parse_error", raw_response=raw[:500])
            return _regex_fallback_extract(text, language)

    if use_llm_fallback and settings.llm_intent_enabled and settings.openai_api_key:
        try:
            return _llm_classify(text, language)
        except Exception as e:
            logger.warning(
                "llm_classification_failed_using_regex",
                error=str(e),
            )
            return _regex_fallback_extract(text, language)

    return _regex_fallback_extract(text, language)
