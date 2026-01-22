from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Callable

from pydantic import BaseModel, ValidationError

from app.agent.models import Intent, ReservationRequest


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
    if re.search(r"(book|reserve|reservation|заброн|брон|rezerv|rezer)", lowered):
        return Intent.create_reservation
    if re.search(r"(change|update|move|измен|перен|змін|zmeni|upravi)", lowered):
        return Intent.update_reservation
    if re.search(r"(cancel|отмен|скас|zruš|cancel)", lowered):
        return Intent.cancel_reservation
    if re.search(r"(menu|меню|страв|jedlo|jedálny|ponuka)", lowered):
        return Intent.menu_question
    if re.search(r"(hours|open|close|работ|відкрит|otvár|hodin|час)", lowered):
        return Intent.hours_info
    return Intent.generic


def _fallback_extract(text: str, language: str | None) -> IntentExtraction:
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


def classify_intent_and_entities(
    text: str,
    language: str | None = None,
    llm: Callable[[str], str] | None = None,
) -> IntentExtraction:
    if llm is None:
        return _fallback_extract(text, language)
    prompt = build_intent_prompt(text, language)
    raw = llm(prompt)
    try:
        payload = json.loads(raw)
        return IntentExtraction.model_validate(payload)
    except (json.JSONDecodeError, ValidationError):
        return _fallback_extract(text, language)
