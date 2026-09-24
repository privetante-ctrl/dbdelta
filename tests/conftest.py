import os
import re
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from tests.support.databases import POSTGRES_URL_VARIABLE, load_sqlite_connection
from tests.support.fixtures import fixture_pairs

from dbdelta.dialects import Dialect
from dbdelta.loaders import LoadResult

LiveSQLite = Callable[[str], LoadResult]
Snapshot = Callable[[Path, str], None]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Rewrite expected SQL files instead of comparing against them.",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize tests over the fixture pairs of the dialect they ask for."""
    parameters = (("sqlite_pair", Dialect.SQLITE), ("postgres_pair", Dialect.POSTGRESQL))
    for argument, dialect in parameters:
        if argument in metafunc.fixturenames:
            pairs = fixture_pairs(dialect)
            metafunc.parametrize(argument, pairs, ids=[pair.id for pair in pairs])


@pytest.fixture
def live_sqlite() -> Iterator[LiveSQLite]:
    """Execute DDL in a fresh in-memory SQLite database and load it back."""
    connections: list[sqlite3.Connection] = []

    def load(ddl: str) -> LoadResult:
        connection = sqlite3.connect(":memory:")
        connections.append(connection)
        connection.executescript(ddl)
        return load_sqlite_connection(connection)

    yield load
    for connection in connections:
        connection.close()


@pytest.fixture
def snapshot(request: pytest.FixtureRequest) -> Snapshot:
    """Compare text with a file, or rewrite the file when run with --update-snapshots."""
    update = bool(request.config.getoption("--update-snapshots"))

    def check(path: Path, actual: str) -> None:
        if update:
            path.write_text(actual, encoding="utf-8")
        elif not path.exists():
            pytest.fail(f"{path} does not exist; run pytest --update-snapshots to create it")
        else:
            assert actual == path.read_text(encoding="utf-8")

    return check


@pytest.fixture
def postgres(request: pytest.FixtureRequest) -> Iterator[psycopg.Connection]:
    """An autocommit connection whose search_path is a fresh, test-owned schema."""
    url = os.environ.get(POSTGRES_URL_VARIABLE)
    if not url:
        pytest.skip(f"set {POSTGRES_URL_VARIABLE} to run PostgreSQL tests")
    schema = "dbdelta_" + re.sub(r"\W+", "_", request.node.name).lower()[:50]
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        connection.execute(f'CREATE SCHEMA "{schema}"')
        connection.execute(f'SET search_path = "{schema}"')
        yield connection
        connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
