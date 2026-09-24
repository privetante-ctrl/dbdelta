"""Connect to a live database named by a SQLAlchemy URL and load its schema."""

import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from dbdelta.dialects import Dialect
from dbdelta.loaders.base import LoadError, LoadResult
from dbdelta.loaders.sqlite import load_sqlite

_URL_SCHEMES = {
    "postgresql": Dialect.POSTGRESQL,
    "postgres": Dialect.POSTGRESQL,
    "sqlite": Dialect.SQLITE,
}


def is_url(source: str) -> bool:
    """Tell a database URL from a file path."""
    return "://" in source


def dialect_from_url(url: str) -> Dialect:
    """Return the dialect of a database URL such as ``postgresql+psycopg://...``."""
    scheme = url.partition("://")[0].partition("+")[0].lower()
    try:
        return _URL_SCHEMES[scheme]
    except KeyError:
        supported = ", ".join(sorted(_URL_SCHEMES))
        raise LoadError(
            f"unsupported database URL scheme {scheme!r}; expected one of: {supported}"
        ) from None


def load_database(url: str) -> LoadResult:
    """Load the schema of the database at ``url`` without modifying it."""
    dialect = dialect_from_url(url)
    if dialect is not Dialect.SQLITE:
        raise LoadError(f"reading a live {dialect} database is not supported yet")
    engine = _sqlite_engine(url)
    try:
        with engine.connect() as connection:
            return load_sqlite(connection)
    except SQLAlchemyError as error:
        raise LoadError(f"cannot read {url}: {error}") from error
    finally:
        engine.dispose()


def _sqlite_engine(url: str) -> Engine:
    try:
        database = make_url(url).database
    except (ArgumentError, ValueError) as error:
        raise LoadError(f"invalid database URL {url!r}: {error}") from error
    if not database or database == ":memory:":
        raise LoadError("an in-memory SQLite database is always empty; use a database file")
    path = Path(database)
    if not path.is_file():
        # sqlite3 would silently create an empty database, which reads as "drop every table".
        raise LoadError(f"SQLite database file not found: {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    # NullPool closes the connection as soon as the single read is done.
    return create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(uri, uri=True), poolclass=NullPool
    )
