"""The migration SQL for every fixture pair, with its risk notes, compared with a stored file.

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
from dbdelta.risk import RiskContext, assess

Snapshot = Callable[[Path, str], None]


def migration_sql(pair: FixturePair, dialect: Dialect) -> str:
    source = load_ddl(pair.a, dialect).schema
    target = load_ddl(pair.b, dialect).schema
    changes = diff_schemas(source, target, dialect)
    plan = plan_migration(changes, source, target, dialect)
    findings = assess(changes, RiskContext(dialect, source, target))
    return emit_migration(plan, findings=findings).render()


def test_postgresql_migration(postgres_pair: FixturePair, snapshot: Snapshot) -> None:
    dialect = Dialect.POSTGRESQL
    snapshot(postgres_pair.expected(dialect), migration_sql(postgres_pair, dialect))


def test_sqlite_migration(sqlite_pair: FixturePair, snapshot: Snapshot) -> None:
    dialect = Dialect.SQLITE
    snapshot(sqlite_pair.expected(dialect), migration_sql(sqlite_pair, dialect))
