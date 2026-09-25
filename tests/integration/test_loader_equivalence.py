"""A schema file and the database created from it must load into the same model.

The live loader reads column types, nullability, defaults and keys from SQLite's own
catalog, so these tests check dbdelta's DDL parser and normalization against SQLite.
"""

from collections.abc import Callable

import psycopg
import pytest
from tests.support.databases import load_postgres_connection

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


POSTGRES_SCHEMAS = {
    "types": """
        CREATE TABLE t (
            a int, b int4, c int8, d smallint, e varchar(255), f varchar, g text, h char(3),
            i char, j real, k float8, l float(10), m numeric(10, 2), n decimal(5), o bool,
            p bytea, q timestamp, r timestamp(3) with time zone, s date, t2 time, u uuid,
            v json, w jsonb, x text[], y integer[][], z varchar(20)[], aa inet, bb interval
        );
    """,
    "defaults": """
        CREATE TABLE t (
            a int DEFAULT 0, b int DEFAULT -1, c numeric(10, 2) DEFAULT 0.5,
            d text DEFAULT 'it''s', e varchar(10) DEFAULT 'x', f boolean DEFAULT true,
            g timestamptz DEFAULT now(), h timestamp DEFAULT CURRENT_TIMESTAMP,
            i text[] DEFAULT '{}', j jsonb DEFAULT '{}', k date DEFAULT '2024-01-01',
            l int DEFAULT NULL, m char(2) DEFAULT 'ab'
        );
    """,
    "negative numbers": """
        CREATE TABLE t (
            a smallint DEFAULT -1, b bigint DEFAULT -1, c numeric(10, 2) DEFAULT -1,
            d real DEFAULT -1, e double precision DEFAULT -1.5, f bigint DEFAULT 3000000000,
            g numeric DEFAULT -1.5
        );
    """,
    "identity and serial": """
        CREATE TABLE a (id serial PRIMARY KEY, n bigserial);
        CREATE TABLE b (id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY);
        CREATE TABLE c (id bigint GENERATED BY DEFAULT AS IDENTITY, x smallserial);
    """,
    "shared sequence": """
        CREATE SEQUENCE shared;
        CREATE TABLE t (a int DEFAULT nextval('shared'), b bigint DEFAULT nextval('shared'));
    """,
    "keys and names": """
        CREATE TABLE p (id int PRIMARY KEY, code text NOT NULL, CONSTRAINT p_code UNIQUE (code));
        CREATE TABLE c (
            id int, p_id int, code text,
            CONSTRAINT c_pk PRIMARY KEY (id),
            CONSTRAINT c_p_fk FOREIGN KEY (p_id) REFERENCES p (id),
            FOREIGN KEY (code) REFERENCES p (code) ON DELETE CASCADE ON UPDATE SET NULL,
            UNIQUE (p_id, code)
        );
    """,
    "checks": """
        CREATE TYPE mood AS ENUM ('sad', 'ok');
        CREATE TABLE t (
            status varchar(10) CHECK (status IN ('a', 'b')),
            price numeric(10, 2) CHECK (price > 0),
            n int, m int, d date, mood mood,
            CONSTRAINT range_check CHECK ((n >= 0 AND n < 100) OR n IS NULL),
            CHECK (n + m > 0 OR (n IS NULL AND m IS NULL)),
            CHECK (d > '2020-01-01'),
            CHECK (status <> 'c' AND length(status) > 0),
            CHECK (mood <> 'sad')
        );
    """,
    "indexes": """
        CREATE TABLE t (a int, b text, c int, d jsonb, e varchar(50), f timestamptz);
        CREATE INDEX ix_plain ON t (a);
        CREATE INDEX ix_multi ON t (c DESC, a);
        CREATE UNIQUE INDEX ix_unique ON t (b);
        CREATE INDEX ix_partial ON t (a) WHERE c IS NOT NULL AND b <> 'x';
        CREATE INDEX ix_expr ON t (lower(b), (a + c));
        CREATE INDEX ix_varchar ON t (lower(e)) WHERE e IN ('p', 'q');
        CREATE INDEX ix_gin ON t USING gin (d);
        CREATE INDEX ix_brin ON t USING brin (f);
        CREATE INDEX ON t (e);
    """,
    "enums and quoted names": """
        CREATE TYPE "Status" AS ENUM ('new', 'done');
        CREATE TABLE "Order" ("Id" int PRIMARY KEY, "select" "Status" DEFAULT 'new',
                              "my col" text);
        CREATE INDEX "My Index" ON "Order" ("my col", "select");
    """,
    "altered tables": """
        CREATE TABLE p (id int);
        ALTER TABLE p ADD CONSTRAINT p_pkey PRIMARY KEY (id);
        CREATE TABLE c (p_id int, note text);
        ALTER TABLE c ADD COLUMN extra int NOT NULL DEFAULT 1;
        ALTER TABLE c ADD CONSTRAINT c_p_fkey FOREIGN KEY (p_id) REFERENCES p (id);
        ALTER TABLE c ALTER COLUMN note SET DEFAULT 'n/a';
    """,
}


@pytest.mark.postgres
@pytest.mark.parametrize("ddl", POSTGRES_SCHEMAS.values(), ids=POSTGRES_SCHEMAS.keys())
def test_postgres_file_and_database_load_equally(ddl: str, postgres: psycopg.Connection) -> None:
    postgres.execute(ddl)
    from_file = load_ddl(ddl, Dialect.POSTGRESQL)
    from_database = load_postgres_connection(postgres)

    # PostgreSQL names every constraint, so compare as the diff does rather than with ==.
    assert (
        diff_schemas(
            from_file.schema, from_database.schema, Dialect.POSTGRESQL, strict_column_order=True
        )
        == ()
    )
