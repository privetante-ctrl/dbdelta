import pytest

from dbdelta.model import DataType
from dbdelta.risk.rules.types import is_narrowing


@pytest.mark.parametrize(
    ("old", "new", "narrowing"),
    [
        (DataType("bigint"), DataType("integer"), True),
        (DataType("integer"), DataType("bigint"), False),
        (DataType("integer"), DataType("numeric", (9, 0)), True),
        (DataType("integer"), DataType("numeric", (10, 0)), False),
        (DataType("double precision"), DataType("real"), True),
        (DataType("real"), DataType("integer"), True),
        (DataType("real"), DataType("double precision"), False),
        (DataType("numeric", (10, 2)), DataType("numeric", (8, 2)), True),
        (DataType("numeric", (10, 2)), DataType("numeric", (10, 1)), True),
        (DataType("numeric", (10, 2)), DataType("numeric", (12, 2)), False),
        (DataType("numeric"), DataType("numeric", (10, 2)), True),
        (DataType("numeric", (10, 2)), DataType("numeric"), False),
        (DataType("numeric", (9, 0)), DataType("integer"), False),
        (DataType("numeric", (10, 0)), DataType("integer"), True),
        (DataType("numeric", (5, 2)), DataType("bigint"), True),
        (DataType("numeric", (10, 2)), DataType("double precision"), True),
        (DataType("varchar", (255,)), DataType("varchar", (50,)), True),
        (DataType("varchar", (50,)), DataType("varchar", (255,)), False),
        (DataType("text"), DataType("varchar", (50,)), True),
        (DataType("varchar", (50,)), DataType("text"), False),
        (DataType("char", (5,)), DataType("varchar", (3,)), True),
        (DataType("timestamp"), DataType("timestamp", (0,)), True),
        (DataType("timestamp", (3,)), DataType("timestamp"), False),
        (DataType("integer"), DataType("text"), False),
        (DataType("text"), DataType("text", is_array=True), False),
    ],
)
def test_narrowing(old: DataType, new: DataType, narrowing: bool) -> None:
    assert is_narrowing(old, new) is narrowing
