"""Round-trip every PostgreSQL fixture pair through a real server.

Build A in a fresh schema, insert its seed rows, read it back with the live loader, apply
the generated migration statement by statement, read the result back and require a strict
diff against B to be empty, the rows of surviving tables to remain and a second plan to be
empty. Each pair runs once in one transaction and once with concurrent index builds.
"""

import psycopg
import pytest
from tests.support.databases import load_postgres_connection, row_counts, run_postgres_script
from tests.support.fixtures import FixturePair

from dbdelta.dialects import Dialect, name_key
from dbdelta.diff import diff_schemas
from dbdelta.emit import EmitOptions, emit_migration
from dbdelta.loaders import load_ddl
from dbdelta.plan import plan_migration
from dbdelta.risk import RiskContext, assess

PG = Dialect.POSTGRESQL

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("concurrent_indexes", [False, True], ids=["transactional", "concurrent"])
def test_postgres_round_trip(
    postgres_pair: FixturePair, postgres: psycopg.Connection, concurrent_indexes: bool
) -> None:
    postgres.execute(postgres_pair.a + (postgres_pair.seed or ""))
    target = load_ddl(postgres_pair.b, PG).schema
    loaded = load_postgres_connection(postgres)
    source = loaded.schema
    kept = [
        table.name
        for table in source.tables
        if any(name_key(t.name, PG) == name_key(table.name, PG) for t in target.tables)
    ]
    rows_before = row_counts(postgres, kept)

    changes = diff_schemas(source, target, PG)
    plan = plan_migration(changes, source, target, PG)
    context = RiskContext(
        PG, source, target, loaded.row_estimates, concurrent_indexes=concurrent_indexes
    )
    options = EmitOptions(concurrent_indexes=concurrent_indexes)
    run_postgres_script(postgres, emit_migration(plan, options, assess(changes, context)))

    result = load_postgres_connection(postgres).schema
    assert diff_schemas(result, target, PG, strict_column_order=True) == ()
    again = plan_migration(diff_schemas(result, target, PG), result, target, PG)
    assert emit_migration(again).is_empty
    assert row_counts(postgres, kept) == rows_before
