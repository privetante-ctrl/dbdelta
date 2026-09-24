"""dbdelta's prediction of table rewrites, checked against PostgreSQL itself.

A rewrite gives the table a new relfilenode, which is how PostgreSQL shows it happened.
"""

import psycopg
import pytest

from dbdelta.dialects import Dialect
from dbdelta.dialects.postgresql import rewrites_table
from dbdelta.loaders.normalize import parse_type

pytestmark = pytest.mark.postgres

CHANGES = [
    ("integer", "bigint"),
    ("bigint", "integer"),
    ("varchar(10)", "varchar(20)"),
    ("varchar(20)", "varchar(10)"),
    ("varchar(10)", "varchar"),
    ("varchar", "varchar(10)"),
    ("varchar(10)", "text"),
    ("text", "varchar"),
    ("text", "varchar(10)"),
    ("numeric(10,2)", "numeric(12,2)"),
    ("numeric(10,2)", "numeric(12,3)"),
    ("numeric(10,2)", "numeric"),
    ("numeric", "numeric(10,2)"),
    ("timestamp(3)", "timestamp"),
    ("timestamp", "timestamp(3)"),
    ("timestamp", "timestamptz"),
    ("char(3)", "char(5)"),
    ("char(3)", "text"),
    ("integer", "text"),
    ("real", "double precision"),
    ("text[]", "varchar[]"),
]


@pytest.mark.parametrize(("old", "new"), CHANGES, ids=[f"{old}->{new}" for old, new in CHANGES])
def test_rewrite_prediction_matches_postgresql(
    postgres: psycopg.Connection, old: str, new: str
) -> None:
    # In UTC PostgreSQL skips the timestamptz rewrite; dbdelta assumes any time zone.
    postgres.execute("SET timezone = 'Europe/Berlin'")
    postgres.execute(f"CREATE TABLE t (a {old})")
    postgres.execute("INSERT INTO t VALUES (NULL)")
    before = postgres.execute("SELECT pg_relation_filenode('t')").fetchone()
    postgres.execute(f"ALTER TABLE t ALTER COLUMN a TYPE {new}")
    after = postgres.execute("SELECT pg_relation_filenode('t')").fetchone()

    predicted = rewrites_table(
        parse_type(old, Dialect.POSTGRESQL), parse_type(new, Dialect.POSTGRESQL)
    )
    assert predicted == (before != after)
