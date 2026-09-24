import pytest

from dbdelta.dialects.postgresql import (
    backs_foreign_key,
    default_name,
    has_volatile_default,
    is_builtin,
    needs_explicit_cast,
    rewrites_table,
)
from dbdelta.model import Column, DataType, ForeignKey, Index, IndexElement, Schema, Table

LONG_TABLE = "a" * 40
LONG_COLUMN = "b" * 40


@pytest.mark.parametrize(
    ("table", "columns", "suffix", "expected"),
    [
        # Expected names were taken from PostgreSQL 16.
        ("p", [], "pkey", "p_pkey"),
        ("p", ["x", "y"], "key", "p_x_y_key"),
        (LONG_TABLE, [LONG_COLUMN], "fkey", "a" * 29 + "_" + "b" * 28 + "_fkey"),
        (LONG_TABLE, [LONG_COLUMN], "key", "a" * 29 + "_" + "b" * 29 + "_key"),
        (LONG_TABLE, ["c"], "check", LONG_TABLE + "_c_check"),
        (LONG_TABLE, [], "check", LONG_TABLE + "_check"),
        (LONG_TABLE, [LONG_COLUMN, "c"], "idx", "a" * 29 + "_" + "b" * 29 + "_idx"),
        ("t", ["é" * 40], "key", "t_" + "é" * 28 + "_key"),
    ],
)
def test_default_names_match_postgresql(
    table: str, columns: list[str], suffix: str, expected: str
) -> None:
    name = default_name(table, columns, suffix)

    assert name == expected
    assert len(name.encode()) <= 63


@pytest.mark.parametrize(
    ("old", "new", "explicit"),
    [
        (DataType("integer"), DataType("bigint"), False),
        (DataType("bigint"), DataType("smallint"), False),
        (DataType("numeric", (10, 2)), DataType("real"), False),
        (DataType("varchar", (10,)), DataType("varchar", (20,)), False),
        (DataType("integer"), DataType("text"), False),
        (DataType("mood"), DataType("varchar", (10,)), False),
        (DataType("timestamp"), DataType("timestamptz"), False),
        (DataType("date"), DataType("timestamp"), False),
        (DataType("text", is_array=True), DataType("varchar", is_array=True), False),
        (DataType("text"), DataType("integer"), True),
        (DataType("text"), DataType("date"), True),
        (DataType("integer"), DataType("boolean"), True),
        (DataType("text"), DataType("mood"), True),
        (DataType("json"), DataType("jsonb"), True),
        (DataType("text"), DataType("text", is_array=True), True),
    ],
)
def test_explicit_casts(old: DataType, new: DataType, explicit: bool) -> None:
    assert needs_explicit_cast(old, new) is explicit


def test_builtin_types() -> None:
    assert is_builtin(DataType("double precision"))
    assert not is_builtin(DataType("mood"))


@pytest.mark.parametrize(
    ("old", "new", "rewrites"),
    [
        (DataType("varchar", (10,)), DataType("varchar", (20,)), False),
        (DataType("varchar", (20,)), DataType("varchar", (10,)), True),
        (DataType("varchar", (10,)), DataType("text"), False),
        (DataType("text"), DataType("varchar", (10,)), True),
        (DataType("numeric", (10, 2)), DataType("numeric", (12, 2)), False),
        (DataType("numeric", (10, 2)), DataType("numeric", (12, 3)), True),
        (DataType("numeric", (10, 2)), DataType("numeric"), False),
        (DataType("char", (3,)), DataType("char"), True),
        (DataType("integer"), DataType("bigint"), True),
        (DataType("text", is_array=True), DataType("varchar", is_array=True), True),
        (DataType("text"), DataType("text", is_array=True), True),
    ],
)
def test_table_rewrites(old: DataType, new: DataType, rewrites: bool) -> None:
    assert rewrites_table(old, new) is rewrites


@pytest.mark.parametrize(
    ("default", "volatile"),
    [
        ("gen_random_uuid()", True),
        ("RANDOM() * 10", True),
        ("NEXTVAL('seq'::regclass)", True),
        ("CURRENT_TIMESTAMP", False),
        ("'random()'", False),
        ("0", False),
    ],
)
def test_volatile_defaults(default: str, volatile: bool) -> None:
    assert has_volatile_default(default) is volatile


def test_unique_indexes_backing_foreign_keys() -> None:
    parent = Table(
        "p",
        (Column("code", DataType("text")),),
        indexes=(Index("ux", (IndexElement("code"),), unique=True),),
    )
    child = Table(
        "c",
        (Column("code", DataType("text")),),
        foreign_keys=(ForeignKey(("code",), "p", ("code",)),),
    )
    schema = Schema((parent, child))

    assert backs_foreign_key(schema, "p", parent.indexes[0])
    assert not backs_foreign_key(schema, "p", Index("ix", (IndexElement("code"),)))
    assert not backs_foreign_key(Schema((parent,)), "p", parent.indexes[0])
