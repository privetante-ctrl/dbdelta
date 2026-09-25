"""Which steps of a down migration cannot bring back what the up migration destroyed.

A down migration is the diff from the desired schema back to the current one, so it
restores the structure: a column the up migration dropped is added again. It cannot restore
the data that went with it, and running it blindly would leave empty columns and tables
where the data used to be. Such steps are marked IRREVERSIBLE.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from dbdelta.diff import AddColumn, AddTable, AlterColumnType, Change
from dbdelta.model import DataType

_INTEGERS = frozenset({"smallint", "integer", "bigint"})
_TEXT = frozenset({"text", "varchar"})
_TIMES = frozenset({"time", "timetz", "timestamp", "timestamptz", "interval"})
_DEFAULT_TIME_PRECISION = 6

# Types whose values all have a text form that converts back to the same value.
_TEXT_ROUND_TRIP = _INTEGERS | _TIMES | {"numeric", "boolean", "date", "uuid"}

# Types whose values fail to convert rather than change when they no longer fit.
_CHECKED_LENGTH = frozenset({"varchar", "char", "bit", "varbit"})


@dataclass(frozen=True, slots=True)
class Irreversible:
    """A step of a down migration that restores structure but not the data that was in it."""

    change: Change
    reason: str


def irreversible_changes(down: Sequence[Change]) -> tuple[Irreversible, ...]:
    """The steps of the down migration ``down`` that cannot restore lost data.

    Every table or column that ``down`` adds was dropped by the up migration together with
    its data, and every type change in ``down`` reverses one of the up migration, which
    lost data unless it kept every value exactly.
    """
    found = []
    for change in down:
        match change:
            case AddTable(table):
                found.append(
                    Irreversible(
                        change,
                        f"The up migration dropped table {table.name} with its rows; this "
                        "creates it again, empty.",
                    )
                )
            case AddColumn(table, column):
                filled = f"set to {column.default}" if column.default else "NULL"
                found.append(
                    Irreversible(
                        change,
                        f"The up migration dropped {table}.{column.name} with its values; "
                        f"this adds it again with every value {filled}.",
                    )
                )
            case AlterColumnType(table, column, old, new) if not keeps_values(new, old):
                found.append(
                    Irreversible(
                        change,
                        f"The up migration converted {table}.{column} from {new} to {old}, "
                        "which may have rounded, cut or reformatted values; converting back "
                        "does not restore them.",
                    )
                )
    return tuple(found)


def keeps_values(old: DataType, new: DataType) -> bool:
    """Whether converting a column from ``old`` to ``new`` leaves every value as it was.

    Conversions either keep a value or fail on it: a value too long for a varchar or too
    large for an integer fails the migration rather than being cut. Conversions that may
    round (numeric scale, time precision, floats), cut (timestamps to dates) or reformat
    (text to numbers) lose information. Anything not known to be safe counts as losing it.
    """
    if old == new:
        return True
    if old.is_array != new.is_array:
        return False
    if old.name == new.name:
        return _modifier_keeps_values(old, new)
    if old.name in _INTEGERS:
        # Integers that do not fit a smaller integer or numeric type fail with an overflow.
        return new.name in _INTEGERS or new.name == "numeric"
    if old.name in _TEXT and new.name in _TEXT:
        return True
    if new.name in _TEXT and not new.params:
        return old.name in _TEXT_ROUND_TRIP
    return old.name == "date" and new.name in ("timestamp", "timestamptz")


def _modifier_keeps_values(old: DataType, new: DataType) -> bool:
    if old.name in _CHECKED_LENGTH:
        return True
    if old.name == "numeric":
        return not new.params or (bool(old.params) and new.params[1] >= old.params[1])
    if old.name in _TIMES:
        return _precision(new) >= _precision(old)
    return False


def _precision(data_type: DataType) -> int:
    return data_type.params[0] if data_type.params else _DEFAULT_TIME_PRECISION
