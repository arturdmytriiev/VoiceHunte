from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from app.core.config import settings
from app.db.pool import get_pool


class ConversationStore:
    def __init__(
        self,
        dsn: str | None = None,
        pool: ConnectionPool | None = None,
    ) -> None:
        self.dsn = dsn or settings.postgres_dsn
        self._pool: ConnectionPool | None = pool
        self._use_shared_pool = pool is None and dsn is None
        self._tables_ensured = False
        if dsn is not None and pool is None:
            self._pool = ConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=1,
                kwargs={"row_factory": dict_row},
                check=ConnectionPool.check_connection,
            )
        if self._pool is not None and settings.db_auto_create:
            self._ensure_tables()
            self._tables_ensured = True

    @property
    def pool(self) -> ConnectionPool:
        if self._pool is None:
            if self._use_shared_pool:
                self._pool = get_pool()
            else:
                raise RuntimeError("Database pool not initialized")
        if settings.db_auto_create and not self._tables_ensured:
            self._ensure_tables()
            self._tables_ensured = True
        return self._pool

    def create_turn(
        self,
        *,
        call_id: str,
        language: str | None,
        user_text: str | None,
        intent: str | None,
        tool_calls: list[dict[str, Any]] | None,
        assistant_text: str | None,
        turn_id: int | None = None,
    ) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calls (call_id, started_at, language)
                    VALUES (%(call_id)s, NOW(), %(language)s)
                    ON CONFLICT (call_id)
                    DO UPDATE SET language = COALESCE(EXCLUDED.language, calls.language)
                    """,
                    {"call_id": call_id, "language": language},
                )
                if turn_id is None:
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(turn_id), 0) + 1 AS next_turn_id
                        FROM turns
                        WHERE call_id = %(call_id)s
                        """,
                        {"call_id": call_id},
                    )
                    row = cur.fetchone()
                    turn_id = int(row["next_turn_id"])

                cur.execute(
                    """
                    INSERT INTO turns (
                        call_id,
                        turn_id,
                        user_text,
                        intent,
                        tool_calls,
                        assistant_text
                    )
                    VALUES (
                        %(call_id)s,
                        %(turn_id)s,
                        %(user_text)s,
                        %(intent)s,
                        %(tool_calls)s,
                        %(assistant_text)s
                    )
                    """,
                    {
                        "call_id": call_id,
                        "turn_id": turn_id,
                        "user_text": user_text,
                        "intent": intent,
                        "tool_calls": Json(tool_calls) if tool_calls is not None else None,
                        "assistant_text": assistant_text,
                    },
                )
            conn.commit()
        return turn_id

    def record_audio(
        self, *, call_id: str, turn_id: int, path: str, kind: str
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audio_files (call_id, turn_id, path, kind)
                    VALUES (%(call_id)s, %(turn_id)s, %(path)s, %(kind)s)
                    """,
                    {
                        "call_id": call_id,
                        "turn_id": turn_id,
                        "path": path,
                        "kind": kind,
                    },
                )
            conn.commit()

    def next_turn_id(self, call_id: str) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(MAX(turn_id), 0) + 1 AS next_turn_id
                    FROM turns
                    WHERE call_id = %(call_id)s
                    """,
                    {"call_id": call_id},
                )
                row = cur.fetchone()
            conn.commit()
        return int(row["next_turn_id"])

    def _get_conn(self):
        return self.pool.connection()

    def save_recording(
        self,
        *,
        call_id: str,
        recording_sid: str,
        recording_url: str,
        from_number: str | None = None,
        to_number: str | None = None,
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recordings (
                        call_id,
                        recording_sid,
                        recording_url,
                        from_number,
                        to_number
                    )
                    VALUES (%(call_id)s, %(recording_sid)s, %(recording_url)s, %(from_number)s, %(to_number)s)
                    ON CONFLICT (call_id)
                    DO UPDATE SET
                        recording_sid = EXCLUDED.recording_sid,
                        recording_url = EXCLUDED.recording_url,
                        updated_at = NOW()
                    """,
                    {
                        "call_id": call_id,
                        "recording_sid": recording_sid,
                        "recording_url": recording_url,
                        "from_number": from_number,
                        "to_number": to_number,
                    },
                )
            conn.commit()

    def get_recording(self, call_id: str) -> dict[str, Any] | None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        call_id,
                        recording_sid,
                        recording_url,
                        from_number,
                        to_number,
                        created_at,
                        updated_at
                    FROM recordings
                    WHERE call_id = %(call_id)s
                    """,
                    {"call_id": call_id},
                )
                row = cur.fetchone()
            conn.commit()
        return row if row else None

    def update_call_session(
        self,
        *,
        call_id: str,
        from_number: str | None = None,
        to_number: str | None = None,
        status: str | None = None,
        ended_at: bool = False,
    ) -> None:
        """Update call session metadata."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                updates = []
                params: dict[str, Any] = {"call_id": call_id}

                if from_number is not None:
                    updates.append("from_number = %(from_number)s")
                    params["from_number"] = from_number

                if to_number is not None:
                    updates.append("to_number = %(to_number)s")
                    params["to_number"] = to_number

                if status is not None:
                    updates.append("status = %(status)s")
                    params["status"] = status

                if ended_at:
                    updates.append("ended_at = NOW()")

                if updates:
                    cur.execute(
                        f"""
                        UPDATE calls
                        SET {", ".join(updates)}
                        WHERE call_id = %(call_id)s
                        """,
                        params,
                    )
            conn.commit()

    def get_call_session(self, call_id: str) -> dict[str, Any] | None:
        """Get complete call session with all turns and recording."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # Get call metadata
                cur.execute(
                    """
                    SELECT
                        c.call_id,
                        c.started_at,
                        c.ended_at,
                        c.language,
                        c.from_number,
                        c.to_number,
                        c.status,
                        r.recording_sid,
                        r.recording_url
                    FROM calls c
                    LEFT JOIN recordings r ON c.call_id = r.call_id
                    WHERE c.call_id = %(call_id)s
                    """,
                    {"call_id": call_id},
                )
                call_row = cur.fetchone()
                if not call_row:
                    return None

                # Get all turns for this call
                cur.execute(
                    """
                    SELECT
                        turn_id,
                        user_text,
                        intent,
                        tool_calls,
                        assistant_text,
                        created_at
                    FROM turns
                    WHERE call_id = %(call_id)s
                    ORDER BY turn_id
                    """,
                    {"call_id": call_id},
                )
                turns = cur.fetchall()

            conn.commit()

        # Build complete session
        session = dict(call_row)
        session["turns"] = [dict(turn) for turn in turns]

        # Build transcript from turns
        transcript_lines = []
        for turn in turns:
            if turn["user_text"]:
                transcript_lines.append(f"User: {turn['user_text']}")
            if turn["assistant_text"]:
                transcript_lines.append(f"Assistant: {turn['assistant_text']}")
        session["transcript"] = "\n".join(transcript_lines)

        return session

    def list_call_sessions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        from_number: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List call sessions with optional filters."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                where_clauses = []
                params: dict[str, Any] = {"limit": limit, "offset": offset}

                if from_number:
                    where_clauses.append("c.from_number = %(from_number)s")
                    params["from_number"] = from_number

                if status:
                    where_clauses.append("c.status = %(status)s")
                    params["status"] = status

                where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

                cur.execute(
                    f"""
                    SELECT
                        c.call_id,
                        c.started_at,
                        c.ended_at,
                        c.language,
                        c.from_number,
                        c.to_number,
                        c.status,
                        r.recording_url,
                        COUNT(t.turn_id) as turn_count
                    FROM calls c
                    LEFT JOIN recordings r ON c.call_id = r.call_id
                    LEFT JOIN turns t ON c.call_id = t.call_id
                    WHERE {where_sql}
                    GROUP BY c.call_id, r.recording_url
                    ORDER BY c.started_at DESC
                    LIMIT %(limit)s OFFSET %(offset)s
                    """,
                    params,
                )
                rows = cur.fetchall()
            conn.commit()

        return [dict(row) for row in rows]

    def _ensure_tables(self) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS calls (
                        call_id TEXT PRIMARY KEY,
                        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        ended_at TIMESTAMPTZ,
                        language TEXT,
                        from_number TEXT,
                        to_number TEXT,
                        status TEXT DEFAULT 'active'
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS turns (
                        call_id TEXT NOT NULL REFERENCES calls(call_id) ON DELETE CASCADE,
                        turn_id INTEGER NOT NULL,
                        user_text TEXT,
                        intent TEXT,
                        tool_calls JSONB,
                        assistant_text TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (call_id, turn_id)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audio_files (
                        call_id TEXT NOT NULL,
                        turn_id INTEGER NOT NULL,
                        path TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (call_id, turn_id, kind),
                        FOREIGN KEY (call_id, turn_id)
                            REFERENCES turns(call_id, turn_id)
                            ON DELETE CASCADE,
                        CHECK (kind IN ('input', 'output'))
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recordings (
                        call_id TEXT PRIMARY KEY REFERENCES calls(call_id) ON DELETE CASCADE,
                        recording_sid TEXT NOT NULL,
                        recording_url TEXT NOT NULL,
                        from_number TEXT,
                        to_number TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()
