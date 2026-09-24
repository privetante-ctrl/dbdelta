import pytest

from dbdelta.dialects import Dialect
from dbdelta.loaders import LoadError
from dbdelta.loaders.normalize import parse_default, parse_expression
from dbdelta.model import DataType

PG = Dialect.POSTGRESQL
SQLITE = Dialect.SQLITE

INTEGER = DataType("integer")
TEXT = DataType("text")
BOOLEAN = DataType("boolean")


@pytest.mark.parametrize(
    ("dialect", "default", "column_type", "expected"),
    [
        # PostgreSQL reports literal defaults with a cast to the column type.
        (PG, "'x'::text", TEXT, "'x'"),
        (PG, "'x'", TEXT, "'x'"),
        (PG, "'x'::character varying", DataType("varchar", (10,)), "'x'"),
        (PG, "'ab'::bpchar", DataType("char", (3,)), "'ab'"),
        (PG, "'{}'::text[]", DataType("text", is_array=True), "'{}'"),
        (PG, "'ok'::mood", DataType("mood"), "'ok'"),
        # Negative numbers come back as quoted literals.
        (PG, "'-1'::integer", INTEGER, "-1"),
        (PG, "-1", INTEGER, "-1"),
        (PG, "'1.5'::real", DataType("real"), "1.5"),
        (PG, "0", DataType("numeric", (10, 2)), "0"),
        # Casting a string literal to an unbounded string type keeps its value.
        (PG, "'x'::text", DataType("varchar", (5,)), "'x'"),
        (PG, "'x'::character varying", DataType("text"), "'x'"),
        # Other casts may change the value and are kept.
        (PG, "'abcdef'::varchar(3)", DataType("text"), "CAST('abcdef' AS varchar(3))"),
        (PG, "'1'::integer", DataType("text"), "CAST('1' AS integer)"),
        (PG, "lower('X')::text", DataType("varchar"), "CAST(LOWER('X') AS text)"),
        (PG, "true", BOOLEAN, "TRUE"),
        (PG, "'t'", BOOLEAN, "TRUE"),
        (PG, "'off'", BOOLEAN, "FALSE"),
        (PG, "now()", DataType("timestamptz"), "CURRENT_TIMESTAMP"),
        (PG, "CURRENT_TIMESTAMP", DataType("timestamptz"), "CURRENT_TIMESTAMP"),
        (PG, "NULL", TEXT, None),
        (PG, "NULL::character varying", DataType("varchar"), None),
        (SQLITE, "(datetime('now'))", DataType("datetime"), "DATETIME('now')"),
        (SQLITE, "datetime('now')", DataType("datetime"), "DATETIME('now')"),
        (SQLITE, "'0'", INTEGER, "0"),
        (SQLITE, "'abc'", INTEGER, "'abc'"),
        (SQLITE, "1", BOOLEAN, "TRUE"),
        (SQLITE, "'it''s'", TEXT, "'it''s'"),
        (SQLITE, "x'00ff'", DataType("blob"), "x'00ff'"),
        (SQLITE, "'1'", DataType("integer", is_array=True), "'1'"),
    ],
)
def test_defaults_are_canonicalized(
    dialect: Dialect, default: str, column_type: DataType, expected: str | None
) -> None:
    assert parse_default(default, column_type, dialect) == expected


@pytest.mark.parametrize(
    ("dialect", "expression", "expected_sql", "expected_columns"),
    [
        (PG, "AGE > 0", '"age" > 0', {"age"}),
        (PG, '("Age" >= 0)', '"Age" >= 0', {"Age"}),
        (PG, '"order" > 1', '"order" > 1', {"order"}),
        (PG, "lower(email) <> ''", "LOWER(\"email\") <> ''", {"email"}),
        (
            SQLITE,
            "(Age >= 0) AND (\"Name\" <> '')",
            '("age" >= 0) AND ("name" <> \'\')',
            {"age", "name"},
        ),
        (SQLITE, "status IN ('a', 'b')", "\"status\" IN ('a', 'b')", {"status"}),
    ],
)
def test_expressions_fold_and_quote_identifiers(
    dialect: Dialect, expression: str, expected_sql: str, expected_columns: set[str]
) -> None:
    result = parse_expression(expression, dialect)

    assert result.sql == expected_sql
    assert result.columns == expected_columns


def test_differently_spelled_equal_expressions_compare_equal() -> None:
    assert parse_expression("(Age > 0)", PG) == parse_expression('"age" > 0', PG)


@pytest.mark.parametrize("text", ["(", ""])
def test_unparsable_expression_is_a_load_error(text: str) -> None:
    with pytest.raises(LoadError, match="cannot parse expression"):
        parse_expression(text, PG)
