"""Run migrations against real databases."""

import sqlite3
from collections.abc import Iterable

import psycopg
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from dbdelta.emit import Script
from dbdelta.loaders import LoadResult
from dbdelta.loaders.sqlite import load_sqlite


def load_sqlite_connection(connection: sqlite3.Connection) -> LoadResult:
    """Load the schema behind an open sqlite3 connection."""
    engine = create_engine("sqlite://", creator=lambda: connection, poolclass=StaticPool)
    with engine.connect() as sqlalchemy_connection:
        return load_sqlite(sqlalchemy_connection)


def row_counts(
    connection: sqlite3.Connection | psycopg.Connection, tables: Iterable[str]
) -> dict[str, int]:
    counts = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        row = connection.execute(f"SELECT count(*) FROM {quoted}").fetchone()
        assert row is not None
        counts[table] = int(row[0])
    return counts


def run_postgres_script(connection: psycopg.Connection, script: Script) -> None:
    """Execute a script statement by statement, as psql would.

    The connection must be in autocommit mode so that blocks outside transactions, such as
    CREATE INDEX CONCURRENTLY, really run outside one.
    """
    for block in script.blocks:
        if block.transactional:
            connection.execute("BEGIN")
        for statement in block.statements:
            if statement.sql:
                connection.execute(statement.sql)
        if block.transactional:
            connection.execute("COMMIT")
