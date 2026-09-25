"""Round-trip every SQLite fixture pair through a real database.

Build A, insert its seed rows, apply the generated migration, read the schema back and
require it to equal B, with the rows of every surviving table still there. Then apply the
down migration and require the schema to equal A again, with the rows of the tables that
existed all along still there; dropped tables and columns come back empty.

"Equal" follows the dialect: a strict diff (column order included) must be empty. Model
equality would be too strict, because SQLite keeps the spelling a name was declared with
while treating ``Users`` and ``users`` as the same table. After the down migration, columns
that were dropped and added back come last, so column order is not compared there.
"""

import sqlite3
from collections.abc import Iterator

import pytest
from tests.support.databases import load_sqlite_connection, row_counts
from tests.support.fixtures import FixturePair
from tests.support.migrations import surviving_tables

from dbdelta.cli.analysis import migrate
from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.loaders import load_ddl

SQLITE = Dialect.SQLITE


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_sqlite_round_trip(sqlite_pair: FixturePair, connection: sqlite3.Connection) -> None:
    settings = sqlite_pair.settings
    target = load_ddl(sqlite_pair.b, SQLITE).schema
    connection.executescript(sqlite_pair.a + (sqlite_pair.seed or ""))
    source = load_sqlite_connection(connection).schema

    up = migrate(source, target, SQLITE, settings)
    surviving = surviving_tables(up.changes, source, target, SQLITE)
    rows_before = row_counts(connection, [old for old, _ in surviving]).values()
    connection.executescript(up.script.render())

    result = load_sqlite_connection(connection).schema
    assert diff_schemas(result, target, SQLITE, strict_column_order=True) == ()
    assert migrate(result, target, SQLITE, settings).script.is_empty
    assert list(row_counts(connection, [new for _, new in surviving]).values()) == list(rows_before)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_sqlite_down_round_trip(sqlite_pair: FixturePair, connection: sqlite3.Connection) -> None:
    settings = sqlite_pair.settings
    connection.executescript(sqlite_pair.a + (sqlite_pair.seed or ""))
    source = load_sqlite_connection(connection).schema
    target = load_ddl(sqlite_pair.b, SQLITE).schema
    up = migrate(source, target, SQLITE, settings)
    kept = [old for old, _ in surviving_tables(up.changes, source, target, SQLITE)]
    rows_before = row_counts(connection, kept)
    connection.executescript(up.script.render())
    migrated = load_sqlite_connection(connection).schema

    down = migrate(migrated, source, SQLITE, settings, down=True)
    connection.executescript(down.script.render())

    result = load_sqlite_connection(connection).schema
    assert diff_schemas(result, source, SQLITE) == ()
    assert migrate(result, source, SQLITE, settings).script.is_empty
    assert row_counts(connection, kept) == rows_before
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
