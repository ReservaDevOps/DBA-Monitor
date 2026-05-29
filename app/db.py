from collections.abc import Iterator
from contextlib import contextmanager
import os

import psycopg
from psycopg.rows import dict_row

from app.settings import settings


def connection_info() -> dict[str, str]:
    return {
        "host": os.getenv("PGHOST", ""),
        "port": os.getenv("PGPORT", "5432"),
        "database": os.getenv("PGDATABASE", ""),
        "user": os.getenv("PGUSER", ""),
        "sslmode": os.getenv("PGSSLMODE", ""),
    }


@contextmanager
def connect(database: str | None = None) -> Iterator[psycopg.Connection]:
    kwargs = {"row_factory": dict_row}
    if database:
        kwargs["dbname"] = database

    with psycopg.connect(**kwargs) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select set_config('statement_timeout', %s, true)",
                (str(settings.statement_timeout_ms),),
            )
        yield conn


def fetch_all(sql: str, params: tuple | None = None, database: str | None = None) -> list[dict]:
    with connect(database=database) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return list(cur.fetchall())


def fetch_one(sql: str, params: tuple | None = None, database: str | None = None) -> dict | None:
    rows = fetch_all(sql, params, database=database)
    return rows[0] if rows else None
