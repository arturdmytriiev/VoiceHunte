from __future__ import annotations

from app.agent import CallState, run_agent
from app.core.config import settings


def test_run_agent_respects_max_turns_setting(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_turns", 5)
    call_state = CallState(call_id="call-123", language="en")
    for _ in range(6):
        call_state.add_history("user", "I want to book a table")

    updated_state = run_agent(call_state)

    assistant_messages = [msg for msg in updated_state.history if msg.role == "assistant"]
    assert len(assistant_messages) == 5
