from __future__ import annotations

import os
from typing import Iterable

import psycopg
import pytest

from app.core.config import settings
from app.crm.mock_db import CRMPostgresMock
from app.db.conversations import ConversationStore


def _normalize_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg", "postgresql")


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    dsn = os.getenv("POSTGRES_DSN", settings.postgres_dsn)
    normalized = _normalize_dsn(dsn)
    settings.postgres_dsn = normalized
    return normalized


def _truncate_tables(conn: psycopg.Connection, tables: Iterable[str]) -> None:
    table_list = ", ".join(tables)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
    conn.commit()


@pytest.fixture()
def clean_db(postgres_dsn: str):
    ConversationStore(postgres_dsn)
    CRMPostgresMock(postgres_dsn)
    conn = psycopg.connect(postgres_dsn)
    _truncate_tables(
        conn,
        [
            "audio_files",
            "turns",
            "calls",
            "reservations",
            "customer_preferences",
        ],
    )
    yield conn
    _truncate_tables(
        conn,
        [
            "audio_files",
            "turns",
            "calls",
            "reservations",
            "customer_preferences",
        ],
    )
    conn.close()
