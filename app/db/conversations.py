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
        if pool is not None:
            self.pool = pool
        elif dsn is not None:
            self.pool = ConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=1,
                kwargs={"row_factory": dict_row},
                check=ConnectionPool.check_connection,
            )
        else:
            self.pool = get_pool()
        if settings.db_auto_create:
            self._ensure_tables()

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

    def _ensure_tables(self) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS calls (
                        call_id TEXT PRIMARY KEY,
                        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        language TEXT
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
            conn.commit()
