from __future__ import annotations

from typing import Optional

from app.agent.models import Intent, ReservationRequest, ToolResult
from app.agent.state import CallState
from app.crm.base import ReservationCreate, ReservationUpdate
from app.crm.mock_db import CRMPostgresMock


def handle_crm_tools(
    state: CallState,
    crm_adapter: Optional[CRMPostgresMock] = None,
) -> CallState:
    adapter = crm_adapter or CRMPostgresMock()
    intent = state.intent
    entities = state.entities or ReservationRequest()
    if intent == Intent.create_reservation:
        if not (entities.name and entities.datetime and entities.people):
            state.tool_results.append(
                ToolResult(
                    tool="crm_create",
                    payload={},
                    error="missing_required_fields",
                )
            )
            return state
        payload = ReservationCreate(
            name=entities.name,
            datetime=entities.datetime,
            people=entities.people,
        )
        record = adapter.create_reservation(payload)
        state.tool_results.append(
            ToolResult(tool="crm_create", payload=record.model_dump())
        )
        return state
    if intent == Intent.update_reservation:
        if not entities.reservation_id:
            state.tool_results.append(
                ToolResult(
                    tool="crm_update",
                    payload={},
                    error="missing_reservation_id",
                )
            )
            return state
        update_payload = ReservationUpdate(
            name=entities.name,
            datetime=entities.datetime,
            people=entities.people,
        )
        record = adapter.update_reservation(
            entities.reservation_id, update_payload
        )
        state.tool_results.append(
            ToolResult(tool="crm_update", payload=record.model_dump())
        )
        return state
    if intent == Intent.cancel_reservation:
        if not entities.reservation_id:
            state.tool_results.append(
                ToolResult(
                    tool="crm_cancel",
                    payload={},
                    error="missing_reservation_id",
                )
            )
            return state
        record = adapter.cancel_reservation(entities.reservation_id)
        state.tool_results.append(
            ToolResult(tool="crm_cancel", payload=record.model_dump())
        )
    return state
