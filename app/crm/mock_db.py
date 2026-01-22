from __future__ import annotations

from typing import Any

from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.core.config import settings
from app.crm.base import (
    CRMAdapter,
    CustomerPreferences,
    CustomerPreferencesRecord,
    ReservationCreate,
    ReservationRecord,
    ReservationUpdate,
)


class CRMPostgresMock(CRMAdapter):
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or settings.postgres_dsn
        if settings.db_auto_create:
            self._ensure_tables()

    def create_reservation(self, payload: ReservationCreate) -> ReservationRecord:
        query = """
            INSERT INTO reservations (name, reservation_datetime, people, phone, notes, status)
            VALUES (%(name)s, %(reservation_datetime)s, %(people)s, %(phone)s, %(notes)s, 'active')
            RETURNING id, name, reservation_datetime, people, phone, notes, status
        """
        params = {
            "name": payload.name,
            "reservation_datetime": payload.datetime,
            "people": payload.people,
            "phone": payload.phone,
            "notes": payload.notes,
        }
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
        return self._row_to_reservation(row)

    def update_reservation(
        self, reservation_id: int, payload: ReservationUpdate
    ) -> ReservationRecord:
        fields: dict[str, Any] = {}
        if payload.name is not None:
            fields["name"] = payload.name
        if payload.datetime is not None:
            fields["reservation_datetime"] = payload.datetime
        if payload.people is not None:
            fields["people"] = payload.people
        if payload.phone is not None:
            fields["phone"] = payload.phone
        if payload.notes is not None:
            fields["notes"] = payload.notes

        if not fields:
            return self._get_reservation(reservation_id)

        set_clause = ", ".join(f"{key} = %({key})s" for key in fields)
        fields["reservation_id"] = reservation_id
        query = f"""
            UPDATE reservations
            SET {set_clause}, updated_at = NOW()
            WHERE id = %(reservation_id)s
            RETURNING id, name, reservation_datetime, people, phone, notes, status
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, fields)
                row = cur.fetchone()
        return self._row_to_reservation(row)

    def cancel_reservation(self, reservation_id: int) -> ReservationRecord:
        query = """
            UPDATE reservations
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = %(reservation_id)s
            RETURNING id, name, reservation_datetime, people, phone, notes, status
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, {"reservation_id": reservation_id})
                row = cur.fetchone()
        return self._row_to_reservation(row)

    def save_preferences(self, payload: CustomerPreferences) -> CustomerPreferencesRecord:
        query = """
            INSERT INTO customer_preferences (customer_key, preferences, updated_at)
            VALUES (%(customer_key)s, %(preferences)s, NOW())
            ON CONFLICT (customer_key)
            DO UPDATE SET preferences = EXCLUDED.preferences, updated_at = NOW()
            RETURNING customer_key, preferences, updated_at
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    {
                        "customer_key": payload.customer_key,
                        "preferences": Json(payload.preferences),
                    },
                )
                row = cur.fetchone()
        return CustomerPreferencesRecord(**row)

    def _get_conn(self):
        return connect(self.dsn, row_factory=dict_row)

    def _ensure_tables(self) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reservations (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        reservation_datetime TIMESTAMPTZ NOT NULL,
                        people INTEGER NOT NULL,
                        phone TEXT,
                        notes TEXT,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customer_preferences (
                        customer_key TEXT PRIMARY KEY,
                        preferences JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()

    def _get_reservation(self, reservation_id: int) -> ReservationRecord:
        query = """
            SELECT id, name, reservation_datetime, people, phone, notes, status
            FROM reservations
            WHERE id = %(reservation_id)s
        """
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, {"reservation_id": reservation_id})
                row = cur.fetchone()
        return self._row_to_reservation(row)

    @staticmethod
    def _row_to_reservation(row: dict[str, Any]) -> ReservationRecord:
        return ReservationRecord(
            reservation_id=row["id"],
            name=row["name"],
            datetime=row["reservation_datetime"],
            people=row["people"],
            phone=row["phone"],
            notes=row["notes"],
            status=row["status"],
        )
