"""Round-trip every SQLite fixture pair through a real database.

Build A, insert its seed rows, apply the generated migration, read the schema back and
require it to equal B, with the rows of every surviving table still there.

"Equal" follows the dialect: a strict diff (column order included) must be empty. Model
equality would be too strict, because SQLite keeps the spelling a name was declared with
while treating ``Users`` and ``users`` as the same table.
"""

import sqlite3

from tests.support.databases import load_sqlite_connection, row_counts
from tests.support.fixtures import FixturePair

from dbdelta.dialects import Dialect, name_key
from dbdelta.diff import diff_schemas
from dbdelta.emit import emit_migration
from dbdelta.loaders import load_ddl
from dbdelta.plan import plan_migration

SQLITE = Dialect.SQLITE


def test_sqlite_round_trip(sqlite_pair: FixturePair) -> None:
    target = load_ddl(sqlite_pair.b, SQLITE).schema
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sqlite_pair.a + (sqlite_pair.seed or ""))
        source = load_sqlite_connection(connection).schema
        kept = [
            table.name
            for table in source.tables
            if any(name_key(t.name, SQLITE) == name_key(table.name, SQLITE) for t in target.tables)
        ]
        rows_before = row_counts(connection, kept)

        plan = plan_migration(diff_schemas(source, target, SQLITE), source, target, SQLITE)
        connection.executescript(emit_migration(plan).render())

        result = load_sqlite_connection(connection).schema
        assert diff_schemas(result, target, SQLITE, strict_column_order=True) == ()
        again = plan_migration(diff_schemas(result, target, SQLITE), result, target, SQLITE)
        assert emit_migration(again).is_empty
        assert row_counts(connection, kept) == rows_before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
