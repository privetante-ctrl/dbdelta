import pytest

from dbdelta.dialects.sqlite import can_add_column, is_constant
from dbdelta.model import Column, DataType, Identity

INTEGER = DataType("integer")


@pytest.mark.parametrize(
    ("default", "constant"),
    [
        ("NULL", True),
        ("TRUE", True),
        ("-1.5e3", True),
        ("'it''s'", True),
        ("x'00ff'", True),
        ("CURRENT_TIMESTAMP", False),
        ("DATETIME('now')", False),
        ("1 + 2", False),
    ],
)
def test_constant_defaults(default: str, constant: bool) -> None:
    assert is_constant(default) is constant


@pytest.mark.parametrize(
    ("column", "addable"),
    [
        (Column("a", INTEGER), True),
        (Column("a", INTEGER, default="0"), True),
        (Column("a", INTEGER, nullable=False, default="0"), True),
        (Column("a", INTEGER, nullable=False), False),
        (Column("a", DataType("timestamp"), default="CURRENT_TIMESTAMP"), False),
        (Column("a", INTEGER, nullable=False, identity=Identity.AUTOINCREMENT), False),
    ],
)
def test_columns_add_column_accepts(column: Column, addable: bool) -> None:
    assert can_add_column(column) is addable
