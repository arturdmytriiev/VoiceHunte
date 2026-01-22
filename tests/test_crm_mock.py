from __future__ import annotations

from datetime import datetime, timezone

from app.crm.base import ReservationCreate, ReservationUpdate
from app.crm.mock_db import CRMPostgresMock


def test_crm_mock_create_update_cancel(clean_db, postgres_dsn: str) -> None:
    adapter = CRMPostgresMock(postgres_dsn)
    payload = ReservationCreate(
        name="Ivan",
        datetime=datetime(2025, 6, 5, 19, 30, tzinfo=timezone.utc),
        people=3,
        phone="+420123456789",
        notes="Window seat",
    )
    created = adapter.create_reservation(payload)

    assert created.reservation_id > 0
    assert created.status == "active"
    assert created.name == "Ivan"
    assert created.people == 3

    updated = adapter.update_reservation(
        created.reservation_id,
        ReservationUpdate(people=4, notes="Updated notes"),
    )
    assert updated.people == 4
    assert updated.notes == "Updated notes"

    cancelled = adapter.cancel_reservation(created.reservation_id)
    assert cancelled.status == "cancelled"
