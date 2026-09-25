import pytest

from dbdelta.diff import AddColumn, AddTable, AlterColumnType, DropColumn, SetNotNull
from dbdelta.model import Column, DataType, Table
from dbdelta.risk import Irreversible, irreversible_changes, keeps_values


def t(name: str, *params: int, array: bool = False) -> DataType:
    return DataType(name, params, is_array=array)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (t("integer"), t("bigint")),
        (t("bigint"), t("smallint")),
        (t("integer"), t("numeric", 5, 2)),
        (t("varchar", 100), t("varchar", 10)),
        (t("text"), t("varchar", 10)),
        (t("varchar", 10), t("text")),
        (t("numeric", 10, 2), t("numeric", 12, 4)),
        (t("numeric", 10, 2), t("numeric")),
        (t("timestamp", 3), t("timestamp")),
        (t("date"), t("timestamptz")),
        (t("uuid"), t("text")),
        (t("boolean"), t("text")),
        (t("integer", array=True), t("bigint", array=True)),
    ],
)
def test_conversions_that_keep_every_value(old: DataType, new: DataType) -> None:
    assert keeps_values(old, new)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (t("numeric", 10, 2), t("numeric", 10, 0)),
        (t("numeric"), t("numeric", 10, 2)),
        (t("numeric", 10, 2), t("integer")),
        (t("double precision"), t("real")),
        (t("bigint"), t("double precision")),
        (t("timestamp"), t("timestamp", 0)),
        (t("timestamp"), t("date")),
        (t("text"), t("integer")),
        (t("jsonb"), t("text")),
        (t("integer"), t("integer", array=True)),
        (t("mood"), t("text", 3)),
    ],
)
def test_conversions_that_may_lose_values(old: DataType, new: DataType) -> None:
    assert not keeps_values(old, new)


def test_down_steps_that_cannot_restore_data_are_irreversible() -> None:
    table = Table("scores", (Column("id", DataType("integer")),))
    restored_column = AddColumn("users", Column("tier", DataType("integer"), default="1"))
    rounded_back = AlterColumnType("t", "price", DataType("integer"), DataType("numeric", (9, 2)))
    widened_back = AlterColumnType("t", "n", DataType("bigint"), DataType("integer"))

    steps = irreversible_changes(
        [
            AddTable(table),
            restored_column,
            rounded_back,
            widened_back,
            DropColumn("users", Column("x", DataType("text"))),
            SetNotNull("users", "tier"),
        ]
    )

    assert steps == (
        Irreversible(
            AddTable(table),
            "The up migration dropped table scores with its rows; this creates it again, empty.",
        ),
        Irreversible(
            restored_column,
            "The up migration dropped users.tier with its values; this adds it again with "
            "every value set to 1.",
        ),
        Irreversible(
            rounded_back,
            "The up migration converted t.price from numeric(9,2) to integer, which may have "
            "rounded, cut or reformatted values; converting back does not restore them.",
        ),
    )
