"""A schema file and the database created from it must load into the same model.

The live loader reads column types, nullability, defaults and keys from SQLite's own
catalog, so these tests check dbdelta's DDL parser and normalization against SQLite.
"""

from collections.abc import Callable

import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.loaders import LoadResult, load_ddl

LiveSQLite = Callable[[str], LoadResult]

SQLITE_SCHEMAS = {
    "types": """
        CREATE TABLE t (
            a INT, b INTEGER, c INT8, d BIGINT, e SMALLINT, f VARCHAR(255), g VARCHAR,
            h TEXT, i CHAR(3), j REAL, k DOUBLE, l FLOAT, m NUMERIC(10, 2), n DECIMAL(5),
            o BOOLEAN, p BLOB, q DATETIME, r TIMESTAMP, s DATE, u UUID, v JSON,
            w, x "My Type"
        );
    """,
    "defaults": """
        CREATE TABLE t (
            a INT DEFAULT 0, b INT DEFAULT -1, c INT DEFAULT '42', d TEXT DEFAULT 'it''s',
            e REAL DEFAULT 1.5, f BOOLEAN DEFAULT TRUE, g BOOLEAN DEFAULT 0,
            h TIMESTAMP DEFAULT CURRENT_TIMESTAMP, i DATETIME DEFAULT (datetime('now')),
            j TEXT DEFAULT NULL, k BLOB DEFAULT x'00ff', l INT DEFAULT (1 + 2)
        );
    """,
    "nullability": """
        CREATE TABLE t (a INT NOT NULL, b INT NULL, c TEXT, d TEXT PRIMARY KEY);
        CREATE TABLE rowid_alias (id INTEGER PRIMARY KEY, x INT);
    """,
    "keys and names": """
        CREATE TABLE p (
            id INTEGER PRIMARY KEY, code TEXT NOT NULL, CONSTRAINT p_code UNIQUE (code)
        );
        CREATE TABLE c (
            id INTEGER, p_id INTEGER, code TEXT,
            CONSTRAINT c_pk PRIMARY KEY (id),
            CONSTRAINT c_p_fk FOREIGN KEY (p_id) REFERENCES p (id),
            FOREIGN KEY (code) REFERENCES p (code),
            UNIQUE (p_id, code),
            CONSTRAINT c_code_check CHECK (length(code) > 1),
            CHECK (p_id > 0)
        );
    """,
    "referential actions": """
        CREATE TABLE p (id INTEGER PRIMARY KEY, a INT, b INT, UNIQUE (a, b));
        CREATE TABLE c (
            x INT REFERENCES p ON DELETE CASCADE,
            y INT REFERENCES p (id) ON UPDATE SET NULL ON DELETE SET DEFAULT,
            a INT, b INT,
            FOREIGN KEY (a, b) REFERENCES p (a, b) ON DELETE RESTRICT
        );
    """,
    "case-insensitive names": """
        CREATE TABLE "Orgs" (Id INTEGER PRIMARY KEY, Name TEXT);
        CREATE TABLE Users (
            ID INTEGER PRIMARY KEY, ORG INT REFERENCES orgs (id), Email TEXT,
            UNIQUE (EMAIL), CHECK (email <> '')
        );
        CREATE INDEX ix_users ON USERS (lower(EMAIL), org DESC);
    """,
    "indexes": """
        CREATE TABLE t (a INT, b TEXT, c INT);
        CREATE INDEX ix_plain ON t (a);
        CREATE INDEX ix_multi ON t (c DESC, a);
        CREATE UNIQUE INDEX ix_unique ON t (b);
        CREATE INDEX ix_partial ON t (a) WHERE c IS NOT NULL;
        CREATE INDEX ix_expr ON t (lower(b), a + c);
        CREATE INDEX ix_collate ON t (b COLLATE NOCASE);
    """,
    "autoincrement": """
        CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);
    """,
    "without rowid": """
        CREATE TABLE t (a INT, b TEXT, PRIMARY KEY (b, a)) WITHOUT ROWID;
    """,
    "quoted identifiers": """
        CREATE TABLE "order" ("select" INT PRIMARY KEY, "my col" TEXT, "Mixed" INT);
        CREATE INDEX "my index" ON "order" ("my col", "Mixed");
    """,
    "altered table": """
        CREATE TABLE t (a INT);
        ALTER TABLE t ADD COLUMN b TEXT NOT NULL DEFAULT 'x';
        ALTER TABLE t ADD COLUMN c INT REFERENCES t (a);
    """,
}


@pytest.mark.parametrize("ddl", SQLITE_SCHEMAS.values(), ids=SQLITE_SCHEMAS.keys())
def test_sqlite_file_and_database_load_equally(ddl: str, live_sqlite: LiveSQLite) -> None:
    from_file = load_ddl(ddl, Dialect.SQLITE)
    from_database = live_sqlite(ddl)

    assert from_database.schema == from_file.schema
    assert diff_schemas(from_file.schema, from_database.schema, Dialect.SQLITE) == ()
