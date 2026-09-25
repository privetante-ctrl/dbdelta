"""Round-trip every PostgreSQL fixture pair through a real server.

Build A in a fresh schema, insert its seed rows, read it back with the live loader, apply
the generated migration statement by statement, read the result back and require a strict
diff against B to be empty, the rows of surviving tables to remain and a second plan to be
empty. Each pair runs once in one transaction and once with concurrent index builds.

The down migration then has to bring the schema back to A, keeping the rows of the tables
that existed all along. Columns that were dropped and added back come last, so column
order is not compared there.
"""

from dataclasses import replace

import psycopg
import pytest
from tests.support.databases import load_postgres_connection, row_counts, run_postgres_script
from tests.support.fixtures import FixturePair
from tests.support.migrations import surviving_tables

from dbdelta.cli.analysis import migrate
from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.loaders import load_ddl

PG = Dialect.POSTGRESQL

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("concurrent_indexes", [False, True], ids=["transactional", "concurrent"])
def test_postgres_round_trip(
    postgres_pair: FixturePair, postgres: psycopg.Connection, concurrent_indexes: bool
) -> None:
    settings = replace(postgres_pair.settings, concurrent_indexes=concurrent_indexes)
    postgres.execute(postgres_pair.a + (postgres_pair.seed or ""))
    target = load_ddl(postgres_pair.b, PG).schema
    loaded = load_postgres_connection(postgres)
    source = loaded.schema

    up = migrate(source, target, PG, settings, loaded.row_estimates)
    surviving = surviving_tables(up.changes, source, target, PG)
    rows_before = list(row_counts(postgres, [old for old, _ in surviving]).values())
    run_postgres_script(postgres, up.script)

    result = load_postgres_connection(postgres).schema
    assert diff_schemas(result, target, PG, strict_column_order=True) == ()
    assert migrate(result, target, PG, settings).script.is_empty
    assert list(row_counts(postgres, [new for _, new in surviving]).values()) == rows_before


def test_postgres_down_round_trip(postgres_pair: FixturePair, postgres: psycopg.Connection) -> None:
    settings = postgres_pair.settings
    postgres.execute(postgres_pair.a + (postgres_pair.seed or ""))
    source = load_postgres_connection(postgres).schema
    target = load_ddl(postgres_pair.b, PG).schema
    up = migrate(source, target, PG, settings)
    kept = [old for old, _ in surviving_tables(up.changes, source, target, PG)]
    rows_before = row_counts(postgres, kept)
    run_postgres_script(postgres, up.script)
    migrated = load_postgres_connection(postgres).schema

    run_postgres_script(postgres, migrate(migrated, source, PG, settings, down=True).script)

    result = load_postgres_connection(postgres).schema
    assert diff_schemas(result, source, PG) == ()
    assert migrate(result, source, PG, settings).script.is_empty
    assert row_counts(postgres, kept) == rows_before
