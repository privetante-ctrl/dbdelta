"""Generated pairs of schemas migrate both ways through real databases.

For any current schema A and desired schema B: build A, migrate it to B, read the result
back and require it to equal B; then run the down migration and require A again.

SQLite migrates with strict column order, which it achieves by rebuilding tables, so the
column order must match too. PostgreSQL cannot reorder columns and appends added ones.
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing

import psycopg
import pytest
from hypothesis import HealthCheck, given, settings
from tests.support.databases import (
    POSTGRES_URL_VARIABLE,
    load_postgres_connection,
    load_sqlite_connection,
    run_postgres_script,
)
from tests.support.strategies import schema_pairs

from dbdelta.cli.analysis import migrate
from dbdelta.cli.config import Settings
from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.model import Schema

SQLITE = Dialect.SQLITE
PG = Dialect.POSTGRESQL
SETTINGS = Settings()
STRICT = Settings(strict_column_order=True)


@given(pair=schema_pairs())
def test_sqlite_migrates_both_ways(pair: tuple[Schema, Schema]) -> None:
    source, target = pair
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.executescript(migrate(Schema(), source, SQLITE, STRICT).script.render())
        start = load_sqlite_connection(connection).schema
        assert diff_schemas(start, source, SQLITE, strict_column_order=True) == ()

        connection.executescript(migrate(start, target, SQLITE, STRICT).script.render())
        reached = load_sqlite_connection(connection).schema
        assert diff_schemas(reached, target, SQLITE, strict_column_order=True) == ()

        down = migrate(reached, start, SQLITE, STRICT, down=True)
        connection.executescript(down.script.render())
        back = load_sqlite_connection(connection).schema
        assert diff_schemas(back, source, SQLITE, strict_column_order=True) == ()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.fixture(scope="module")
def postgres_database() -> Iterator[psycopg.Connection]:
    url = os.environ.get(POSTGRES_URL_VARIABLE)
    if not url:
        pytest.skip(f"set {POSTGRES_URL_VARIABLE} to run PostgreSQL tests")
    with psycopg.connect(url, autocommit=True) as connection:
        yield connection
        connection.execute("DROP SCHEMA IF EXISTS dbdelta_property CASCADE")


@pytest.mark.postgres
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pair=schema_pairs())
def test_postgresql_migrates_both_ways(
    postgres_database: psycopg.Connection, pair: tuple[Schema, Schema]
) -> None:
    source, target = pair
    connection = postgres_database
    connection.execute("DROP SCHEMA IF EXISTS dbdelta_property CASCADE")
    connection.execute("CREATE SCHEMA dbdelta_property")
    connection.execute("SET search_path = dbdelta_property")

    run_postgres_script(connection, migrate(Schema(), source, PG, SETTINGS).script)
    start = load_postgres_connection(connection).schema
    assert diff_schemas(start, source, PG, strict_column_order=True) == ()

    run_postgres_script(connection, migrate(start, target, PG, SETTINGS).script)
    reached = load_postgres_connection(connection).schema
    assert diff_schemas(reached, target, PG) == ()

    run_postgres_script(connection, migrate(reached, start, PG, SETTINGS, down=True).script)
    back = load_postgres_connection(connection).schema
    assert diff_schemas(back, source, PG) == ()
