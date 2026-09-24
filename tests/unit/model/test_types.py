import pytest

from dbdelta.model import DataType


@pytest.mark.parametrize(
    ("data_type", "expected"),
    [
        (DataType("integer"), "integer"),
        (DataType("varchar", (255,)), "varchar(255)"),
        (DataType("numeric", (10, 2)), "numeric(10,2)"),
        (DataType("text", is_array=True), "text[]"),
        (DataType("varchar", (20,), is_array=True), "varchar(20)[]"),
        (DataType(""), ""),
    ],
)
def test_renders_as_sql(data_type: DataType, expected: str) -> None:
    assert str(data_type) == expected


def test_untyped_column_cannot_have_parameters() -> None:
    with pytest.raises(ValueError, match="untyped"):
        DataType("", (1,))


def test_types_are_hashable_values() -> None:
    assert {DataType("integer"), DataType("integer")} == {DataType("integer")}
