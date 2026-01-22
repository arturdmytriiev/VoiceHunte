from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

_pool: ConnectionPool | None = None


def init_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        max_size = settings.postgres_pool_size + settings.postgres_pool_max_overflow
        _pool = ConnectionPool(
            conninfo=settings.postgres_dsn,
            min_size=1,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            check=ConnectionPool.check_connection,
        )
    return _pool


def get_pool() -> ConnectionPool:
    return init_pool()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
