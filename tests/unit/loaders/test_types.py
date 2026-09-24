"""Type aliases must collapse onto one canonical type, whichever loader reads them."""

import pytest

from dbdelta.dialects import Dialect
from dbdelta.loaders import load_ddl
from dbdelta.loaders.normalize import parse_type
from dbdelta.model import DataType

PG = Dialect.POSTGRESQL
SQLITE = Dialect.SQLITE

CASES = [
    (PG, "int", DataType("integer")),
    (PG, "INTEGER", DataType("integer")),
    (PG, "int4", DataType("integer")),
    (PG, "int8", DataType("bigint")),
    (PG, "int2", DataType("smallint")),
    (PG, "varchar", DataType("varchar")),
    (PG, "character varying(10)", DataType("varchar", (10,))),
    (PG, "text", DataType("text")),
    (PG, "char", DataType("char", (1,))),
    (PG, "character(3)", DataType("char", (3,))),
    (PG, "numeric", DataType("numeric")),
    (PG, "numeric(5)", DataType("numeric", (5, 0))),
    (PG, "decimal(10, 2)", DataType("numeric", (10, 2))),
    (PG, "float4", DataType("real")),
    (PG, "float(24)", DataType("real")),
    (PG, "float(25)", DataType("double precision")),
    (PG, "float", DataType("double precision")),
    (PG, "float8", DataType("double precision")),
    (PG, "bool", DataType("boolean")),
    (PG, "bytea", DataType("bytea")),
    (PG, "timestamp(6)", DataType("timestamp")),
    (PG, "timestamp(3) with time zone", DataType("timestamptz", (3,))),
    (PG, "time without time zone", DataType("time")),
    (PG, "bit", DataType("bit", (1,))),
    (PG, "uuid", DataType("uuid")),
    (PG, "jsonb", DataType("jsonb")),
    (PG, "int[]", DataType("integer", is_array=True)),
    (PG, "integer[][]", DataType("integer", is_array=True)),
    (PG, "varchar(20)[]", DataType("varchar", (20,), is_array=True)),
    (PG, "mood", DataType("mood")),
    (PG, "public.mood", DataType("mood")),
    (PG, '"Mood"', DataType("Mood")),
    (PG, "audit.mood", DataType("audit.mood")),
    (SQLITE, "INT", DataType("integer")),
    (SQLITE, "INT8", DataType("bigint")),
    (SQLITE, "VARCHAR(255)", DataType("varchar", (255,))),
    (SQLITE, "CLOB", DataType("text")),
    (SQLITE, "REAL", DataType("real")),
    (SQLITE, "FLOAT", DataType("real")),
    (SQLITE, "DOUBLE", DataType("double precision")),
    (SQLITE, "NUMERIC(10)", DataType("numeric", (10, 0))),
    (SQLITE, "BOOLEAN", DataType("boolean")),
    (SQLITE, "BLOB", DataType("blob")),
    (SQLITE, "DATETIME", DataType("datetime")),
    (SQLITE, "char", DataType("char")),
    (SQLITE, "UUID", DataType("uuid")),
]


@pytest.mark.parametrize(("dialect", "declared", "expected"), CASES)
def test_catalog_type_names_are_canonicalized(
    dialect: Dialect, declared: str, expected: DataType
) -> None:
    assert parse_type(declared, dialect) == expected


@pytest.mark.parametrize(("dialect", "declared", "expected"), CASES)
def test_ddl_column_types_match_catalog_types(
    dialect: Dialect, declared: str, expected: DataType
) -> None:
    schema = load_ddl(f"CREATE TABLE t (c {declared})", dialect).schema

    assert schema.tables[0].columns[0].type == expected


@pytest.mark.parametrize("dialect", list(Dialect))
def test_varchar_without_length_is_not_text(dialect: Dialect) -> None:
    assert parse_type("varchar", dialect) != parse_type("text", dialect)


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("UNSIGNED BIG INT", DataType("unsigned big int")),
        ("My  Type", DataType("my type")),
        ("", DataType("")),
    ],
)
def test_sqlite_accepts_free_form_type_names(declared: str, expected: DataType) -> None:
    assert parse_type(declared, SQLITE) == expected


def test_types_with_non_numeric_parameters_keep_their_spelling() -> None:
    assert parse_type("geometry(Point, 4326)", PG) == DataType("geometry(point,4326)")
    assert parse_type("interval day to second", PG) == DataType("interval day to second")
