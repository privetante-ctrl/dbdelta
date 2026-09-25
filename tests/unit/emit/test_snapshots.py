"""The migration SQL for every fixture pair, with its notes, compared with stored files.

Both directions are kept: ``expected.<dialect>.sql`` migrates A to B and
``expected.<dialect>.down.sql`` migrates B back to A. Regenerate them with
``pytest --update-snapshots`` and review the diff.
"""

import pytest
from tests.conftest import Snapshot
from tests.support.fixtures import FixturePair

from dbdelta.cli.analysis import migrate
from dbdelta.dialects import Dialect
from dbdelta.loaders import load_ddl

DIRECTIONS = pytest.mark.parametrize("down", [False, True], ids=["up", "down"])


def migration_sql(pair: FixturePair, dialect: Dialect, *, down: bool) -> str:
    source = load_ddl(pair.a, dialect).schema
    target = load_ddl(pair.b, dialect).schema
    if down:
        source, target = target, source
    return migrate(source, target, dialect, pair.settings, down=down).script.render()


@DIRECTIONS
def test_postgresql_migration(postgres_pair: FixturePair, snapshot: Snapshot, down: bool) -> None:
    dialect = Dialect.POSTGRESQL
    snapshot(
        postgres_pair.expected(dialect, down=down), migration_sql(postgres_pair, dialect, down=down)
    )


@DIRECTIONS
def test_sqlite_migration(sqlite_pair: FixturePair, snapshot: Snapshot, down: bool) -> None:
    dialect = Dialect.SQLITE
    snapshot(
        sqlite_pair.expected(dialect, down=down), migration_sql(sqlite_pair, dialect, down=down)
    )
