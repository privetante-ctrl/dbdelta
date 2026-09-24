"""The migration SQL for every fixture pair, compared with its stored expected file.

Regenerate the expected files with ``pytest --update-snapshots`` and review the diff.
"""

from collections.abc import Callable
from pathlib import Path

from tests.support.fixtures import FixturePair

from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.emit import emit_migration
from dbdelta.loaders import load_ddl
from dbdelta.plan import plan_migration

Snapshot = Callable[[Path, str], None]


def migration_sql(pair: FixturePair, dialect: Dialect) -> str:
    source = load_ddl(pair.a, dialect).schema
    target = load_ddl(pair.b, dialect).schema
    plan = plan_migration(diff_schemas(source, target, dialect), source, target, dialect)
    return emit_migration(plan).render()


def test_postgresql_migration(postgres_pair: FixturePair, snapshot: Snapshot) -> None:
    dialect = Dialect.POSTGRESQL
    snapshot(postgres_pair.expected(dialect), migration_sql(postgres_pair, dialect))


def test_sqlite_migration(sqlite_pair: FixturePair, snapshot: Snapshot) -> None:
    dialect = Dialect.SQLITE
    snapshot(sqlite_pair.expected(dialect), migration_sql(sqlite_pair, dialect))
