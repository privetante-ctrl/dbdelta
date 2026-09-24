"""Every PostgreSQL migration generated for a fixture pair must execute cleanly.

Reading the result back and comparing it with B arrives with the live PostgreSQL loader.
"""

import psycopg
import pytest
from tests.support.databases import run_postgres_script
from tests.support.fixtures import FixturePair

from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.emit import EmitOptions, emit_migration
from dbdelta.loaders import load_ddl
from dbdelta.plan import plan_migration

PG = Dialect.POSTGRESQL

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("concurrent_indexes", [False, True], ids=["transactional", "concurrent"])
def test_postgres_migration_executes(
    postgres_pair: FixturePair, postgres: psycopg.Connection, concurrent_indexes: bool
) -> None:
    postgres.execute(postgres_pair.a + (postgres_pair.seed or ""))
    source = load_ddl(postgres_pair.a, PG).schema
    target = load_ddl(postgres_pair.b, PG).schema
    plan = plan_migration(diff_schemas(source, target, PG), source, target, PG)

    run_postgres_script(
        postgres, emit_migration(plan, EmitOptions(concurrent_indexes=concurrent_indexes))
    )
