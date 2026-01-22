from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent.models import AgentResponse, Intent, ReservationRequest, ToolResult


class HistoryMessage(BaseModel):
    role: str
    text: str


class CallState(BaseModel):
    call_id: str
    language: str | None = None
    history: list[HistoryMessage] = Field(default_factory=list)
    last_user_text: str | None = None
    intent: Intent | None = None
    entities: ReservationRequest | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    final_answer: AgentResponse | None = None

    def add_history(self, role: str, text: str) -> None:
        self.history.append(HistoryMessage(role=role, text=text))

    def last_user_message(self) -> str | None:
        if self.last_user_text:
            return self.last_user_text
        for message in reversed(self.history):
            if message.role == "user":
                return message.text
        return None

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump()
