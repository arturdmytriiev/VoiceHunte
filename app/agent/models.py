from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Intent(str, Enum):
    create_reservation = "create_reservation"
    update_reservation = "update_reservation"
    cancel_reservation = "cancel_reservation"
    menu_question = "menu_question"
    hours_info = "hours_info"
    generic = "generic"


class IntentResult(BaseModel):
    intent: Intent


class ReservationRequest(BaseModel):
    name: str | None = None
    datetime: datetime | None = None
    people: int | None = Field(default=None, ge=1)
    reservation_id: int | None = None


class AgentResponse(BaseModel):
    answer_text: str
    actions: list[str] = Field(default_factory=list)
    language: str


class ToolResult(BaseModel):
    tool: str
    payload: dict[str, Any]
    error: str | None = None
