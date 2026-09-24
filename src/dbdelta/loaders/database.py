"""Connect to a live database named by a SQLAlchemy URL and load its schema."""

import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from dbdelta.dialects import Dialect
from dbdelta.loaders.base import LoadError, LoadResult
from dbdelta.loaders.postgresql import load_postgresql
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


def load_database(url: str, schema: str | None = None) -> LoadResult:
    """Load the schema of the database at ``url`` without modifying it.

    ``schema`` selects the PostgreSQL schema to read (``public`` by default).
    """
    dialect = dialect_from_url(url)
    if dialect is Dialect.SQLITE:
        if schema not in (None, "main"):
            raise LoadError("SQLite databases have a single schema; do not pass one")
        engine = _sqlite_engine(url)
    else:
        engine = _postgresql_engine(url)
    try:
        with engine.connect() as connection:
            if dialect is Dialect.SQLITE:
                return load_sqlite(connection)
            return load_postgresql(connection, schema or "public")
    except SQLAlchemyError as error:
        raise LoadError(f"cannot read {_hide_password(url)}: {error}") from error
    finally:
        engine.dispose()


def _postgresql_engine(url: str) -> Engine:
    try:
        parsed = make_url(url)
    except (ArgumentError, ValueError) as error:
        raise LoadError(f"invalid database URL {_hide_password(url)!r}: {error}") from error
    if "+" not in parsed.drivername:
        parsed = parsed.set(drivername="postgresql+psycopg")
    try:
        return create_engine(
            parsed,
            poolclass=NullPool,
            # The loader only reads; the server refuses any write in these sessions.
            connect_args={"options": "-c default_transaction_read_only=on"},
        )
    except ModuleNotFoundError as error:
        raise LoadError(
            "reading PostgreSQL needs a driver: pip install 'dbdelta[postgres]'"
        ) from error


def _hide_password(url: str) -> str:
    try:
        return make_url(url).render_as_string(hide_password=True)
    except (ArgumentError, ValueError):
        return url


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
