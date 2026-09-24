from collections.abc import Callable
from typing import Any

import pytest

from dbdelta.model import (
    CheckConstraint,
    Column,
    DataType,
    EnumType,
    Expression,
    ForeignKey,
    Index,
    IndexElement,
    PrimaryKey,
    Schema,
    Table,
    UniqueConstraint,
)

INTEGER = DataType("integer")
TEXT = DataType("text")


def make_table(name: str = "users", **kwargs: Any) -> Table:
    columns = (Column("id", INTEGER, nullable=False), Column("email", TEXT), Column("age", INTEGER))
    return Table(name, columns, **kwargs)


def test_schema_equality_ignores_declaration_order_of_tables_and_enums() -> None:
    users, orders = make_table("users"), make_table("orders")
    mood, color = EnumType("mood", ("sad", "ok")), EnumType("color", ("red",))

    assert Schema((users, orders), (mood, color)) == Schema((orders, users), (color, mood))
    assert [table.name for table in Schema((users, orders)).tables] == ["orders", "users"]


def test_table_equality_ignores_order_of_constraints_and_indexes() -> None:
    fks = (
        ForeignKey(("id",), "a", ("id",)),
        ForeignKey(("age",), "b", ("id",)),
    )
    uniques = (UniqueConstraint(("email",)), UniqueConstraint(("age",), "uq_age"))
    checks = (
        CheckConstraint(Expression("age > 0")),
        CheckConstraint(Expression("email <> ''")),
    )
    indexes = (
        Index("ix_b", (IndexElement("email"),)),
        Index("ix_a", (IndexElement("age"),)),
    )

    forward = make_table(
        foreign_keys=fks, unique_constraints=uniques, check_constraints=checks, indexes=indexes
    )
    backward = make_table(
        foreign_keys=fks[::-1],
        unique_constraints=uniques[::-1],
        check_constraints=checks[::-1],
        indexes=indexes[::-1],
    )

    assert forward == backward


def test_table_keeps_column_declaration_order() -> None:
    table = make_table()

    assert table.column_names == ("id", "email", "age")
    assert table != Table("users", table.columns[::-1])


def test_column_lookup() -> None:
    table = make_table()

    assert table.column("email") == Column("email", TEXT)
    assert table.column("missing") is None


def test_table_and_enum_lookup() -> None:
    schema = Schema((make_table(),), (EnumType("mood", ("ok",)),))

    assert schema.table("users") == make_table()
    assert schema.table("missing") is None
    assert schema.enum("mood") == EnumType("mood", ("ok",))
    assert schema.enum("missing") is None


@pytest.mark.parametrize(
    ("kwargs", "owner"),
    [
        ({"primary_key": PrimaryKey(("nope",))}, "primary key"),
        ({"foreign_keys": (ForeignKey(("nope",), "t", ("id",)),)}, "foreign key"),
        ({"unique_constraints": (UniqueConstraint(("nope",)),)}, "unique constraint"),
        ({"indexes": (Index("ix", (IndexElement("nope"),)),)}, "index 'ix'"),
    ],
)
def test_references_to_unknown_columns_are_rejected(kwargs: dict[str, Any], owner: str) -> None:
    with pytest.raises(ValueError, match=rf"{owner} of table 'users' .* \['nope'\]"):
        make_table(**kwargs)


def test_expression_index_keys_may_reference_anything() -> None:
    index = Index("ix", (IndexElement(Expression("lower(email)", frozenset({"email"}))),))

    assert make_table(indexes=(index,)).indexes == (index,)


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: Table("t", ()), "has no columns"),
        (lambda: Table("t", (Column("a", INTEGER), Column("a", TEXT))), r"\['a'\] more than once"),
        (lambda: Schema((make_table(), make_table())), r"\['users'\] more than once"),
        (lambda: Schema(enums=(EnumType("e", ("x",)), EnumType("e", ("y",)))), "more than once"),
        (lambda: EnumType("e", ()), "has no values"),
        (lambda: EnumType("e", ("x", "x")), "more than once"),
        (lambda: PrimaryKey(()), "has no columns"),
        (lambda: PrimaryKey(("a", "a")), "more than once"),
        (lambda: UniqueConstraint(()), "has no columns"),
        (lambda: ForeignKey(("a", "b"), "t", ("id",)), "expected 2"),
        (lambda: Index("ix", ()), "has no keys"),
    ],
)
def test_invalid_objects_are_rejected(build: Callable[[], object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build()


def test_expression_equality_ignores_derived_columns() -> None:
    assert Expression("a > b", frozenset({"a", "b"})) == Expression("a > b")
    assert str(Expression("a > b")) == "a > b"


def test_index_columns_include_expression_keys_and_predicate() -> None:
    index = Index(
        "ix",
        (
            IndexElement("id"),
            IndexElement(Expression("lower(email)", frozenset({"email"})), descending=True),
        ),
        where=Expression("age > 18", frozenset({"age"})),
    )

    assert index.columns == {"id", "email", "age"}
    assert Index("ix", (IndexElement("id"),)).columns == {"id"}


def test_model_objects_are_immutable_and_hashable() -> None:
    table = make_table(primary_key=PrimaryKey(("id",)))

    with pytest.raises(AttributeError):
        table.name = "other"  # type: ignore[misc]
    assert hash(Schema((table,))) == hash(Schema((make_table(primary_key=PrimaryKey(("id",))),)))
