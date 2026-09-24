import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from dbdelta.dialects import Dialect
from dbdelta.loaders import LoadError, LoadResult, dialect_from_url, load_database, load_source
from dbdelta.loaders.database import _sqlite_engine
from dbdelta.model import Column, DataType, ForeignKey, Identity, Index, IndexElement

LiveSQLite = Callable[[str], LoadResult]


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "app.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
    return path


def test_load_database_reads_a_sqlite_file(database: Path) -> None:
    result = load_database(f"sqlite:///{database}")

    assert result.schema.table("users") is not None


def test_database_is_opened_read_only(database: Path) -> None:
    engine = _sqlite_engine(f"sqlite:///{database}")
    try:
        with engine.connect() as connection, pytest.raises(OperationalError, match="readonly"):
            connection.execute(text("CREATE TABLE intruder (x INT)"))
    finally:
        engine.dispose()


def test_missing_database_file_is_an_error_and_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"

    with pytest.raises(LoadError, match="SQLite database file not found"):
        load_database(f"sqlite:///{missing}")
    assert not missing.exists()


def test_invalid_url_is_an_error() -> None:
    with pytest.raises(LoadError, match="invalid database URL"):
        load_database("sqlite://:::")


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:"])
def test_in_memory_database_is_rejected(url: str) -> None:
    with pytest.raises(LoadError, match="in-memory"):
        load_database(url)


def test_file_that_is_not_a_database_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "notes.db"
    path.write_text("not a database", encoding="utf-8")

    with pytest.raises(LoadError, match="cannot read"):
        load_database(f"sqlite:///{path}")


@pytest.mark.parametrize(
    ("url", "dialect"),
    [
        ("postgresql://localhost/app", Dialect.POSTGRESQL),
        ("postgresql+psycopg://u:p@localhost/app", Dialect.POSTGRESQL),
        ("postgres://localhost/app", Dialect.POSTGRESQL),
        ("sqlite:///app.db", Dialect.SQLITE),
        ("SQLITE+pysqlite:///app.db", Dialect.SQLITE),
    ],
)
def test_dialect_from_url(url: str, dialect: Dialect) -> None:
    assert dialect_from_url(url) is dialect


def test_unsupported_url_scheme_is_an_error() -> None:
    with pytest.raises(LoadError, match="unsupported database URL scheme 'mysql'"):
        dialect_from_url("mysql://localhost/app")


def test_live_postgresql_is_not_supported_yet() -> None:
    with pytest.raises(LoadError, match="not supported yet"):
        load_database("postgresql://localhost/app")


def test_load_source_dispatches_on_urls_and_files(database: Path, tmp_path: Path) -> None:
    ddl = tmp_path / "schema.sql"
    ddl.write_text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL);")

    from_file = load_source(str(ddl), Dialect.SQLITE)
    from_url = load_source(f"sqlite:///{database}")

    assert from_file.schema == from_url.schema


def test_load_source_needs_a_dialect_for_files(tmp_path: Path) -> None:
    with pytest.raises(LoadError, match="cannot tell which SQL dialect"):
        load_source(str(tmp_path / "schema.sql"))


def test_load_source_rejects_a_conflicting_dialect(database: Path) -> None:
    with pytest.raises(LoadError, match="is a sqlite database, not postgresql"):
        load_source(f"sqlite:///{database}", Dialect.POSTGRESQL)


def test_live_loader_reads_what_the_inspector_misses(live_sqlite: LiveSQLite) -> None:
    schema = live_sqlite(
        """
        CREATE TABLE orgs (id INTEGER PRIMARY KEY AUTOINCREMENT, code UUID);
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT,
            org_id INTEGER REFERENCES orgs ON DELETE CASCADE,
            UNIQUE (EMAIL)
        );
        CREATE UNIQUE INDEX ix_email ON users (lower(email)) WHERE org_id IS NOT NULL;
        """
    ).schema
    orgs, users = schema.table("orgs"), schema.table("users")

    assert orgs is not None
    assert users is not None
    assert orgs.columns == (
        Column("id", DataType("integer"), nullable=False, identity=Identity.AUTOINCREMENT),
        Column("code", DataType("uuid")),
    )
    assert users.foreign_keys[0].on_delete == "CASCADE"
    assert users.foreign_keys[0].ref_columns == ("id",)
    assert users.unique_constraints[0].columns == ("email",)
    assert users.indexes[0].where is not None


def test_generated_columns_are_reported(live_sqlite: LiveSQLite) -> None:
    result = live_sqlite("CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a * 2) VIRTUAL)")

    assert "column t.b: generated column is treated as a regular one" in result.warnings


def test_constraint_names_come_from_the_stored_ddl(live_sqlite: LiveSQLite) -> None:
    schema = live_sqlite(
        """
        CREATE TABLE p (id INTEGER, CONSTRAINT p_pk PRIMARY KEY (id));
        CREATE TABLE c (a INT CONSTRAINT c_p_fk REFERENCES p, b INT REFERENCES p (id),
                        CONSTRAINT c_b_uq UNIQUE (b));
        CREATE INDEX ix ON c (a DESC);
        """
    ).schema
    parent, child = schema.table("p"), schema.table("c")

    assert parent is not None
    assert child is not None
    assert parent.primary_key is not None
    assert parent.primary_key.name == "p_pk"
    assert child.foreign_keys == (
        ForeignKey(("a",), "p", ("id",), name="c_p_fk"),
        ForeignKey(("b",), "p", ("id",)),
    )
    assert child.unique_constraints[0].name == "c_b_uq"
    assert child.indexes == (Index("ix", (IndexElement("a", descending=True),)),)


def test_virtual_tables_and_their_shadow_tables_are_skipped(live_sqlite: LiveSQLite) -> None:
    result = live_sqlite(
        "CREATE TABLE docs (id INTEGER PRIMARY KEY, body TEXT);"
        "CREATE VIRTUAL TABLE docs_fts USING fts5(body, content='docs', content_rowid='id');"
    )

    assert [table.name for table in result.schema.tables] == ["docs"]
    assert result.warnings == (
        "skipped virtual table 'docs_fts': virtual tables are not supported",
    )
