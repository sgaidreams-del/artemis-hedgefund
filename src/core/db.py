"""Database connection pool. Postgres (native Homebrew install, see scripts/init.sql)."""
from __future__ import annotations

import atexit
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from .config import env

_pool: ConnectionPool | None = None


def get_dsn() -> str:
    # No password fallback: a hardcoded default would ship to every install.
    # Run ./install.sh (or scripts/configure.py) to generate one into .env.
    return make_conninfo(
        host=env("POSTGRES_HOST", "127.0.0.1"),
        port=env("POSTGRES_PORT", "5432"),
        dbname=env("POSTGRES_DB", "artemis"),
        user=env("POSTGRES_USER", "artemis"),
        password=env("POSTGRES_PASSWORD", required=True),
    )


def init_pool(min_size: int = 1, max_size: int = 10) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(get_dsn(), min_size=min_size, max_size=max_size, open=True)
        atexit.register(_pool.close)
    return _pool


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    """Borrow a connection from the pool."""
    pool = init_pool()
    with pool.connection() as c:
        yield c


def ping() -> bool:
    """Health check."""
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:
        return False
