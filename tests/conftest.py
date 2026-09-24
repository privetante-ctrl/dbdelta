import sqlite3
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from dbdelta.loaders import LoadResult
from dbdelta.loaders.sqlite import load_sqlite

LiveSQLite = Callable[[str], LoadResult]


@pytest.fixture
def live_sqlite() -> Iterator[LiveSQLite]:
    """Execute DDL in a fresh in-memory SQLite database and load it back."""
    connections: list[sqlite3.Connection] = []

    def load(ddl: str) -> LoadResult:
        raw = sqlite3.connect(":memory:")
        connections.append(raw)
        raw.executescript(ddl)
        engine = create_engine("sqlite://", creator=lambda: raw, poolclass=StaticPool)
        with engine.connect() as connection:
            return load_sqlite(connection)

    yield load
    for raw in connections:
        raw.close()
