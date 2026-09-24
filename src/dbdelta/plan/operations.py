"""Operations a plan adds on top of the diff's changes."""

from dataclasses import dataclass
from typing import TypeAlias

from dbdelta.diff import Change, describe
from dbdelta.model import Column, EnumType, Table


@dataclass(frozen=True, slots=True)
class RebuildTable:
    """Recreate a table in its target form and copy its rows over.

    Used where ALTER TABLE cannot apply ``changes`` in place, as in SQLite. The rebuild
    replaces those changes, including the table's index changes.
    """

    old: Table
    new: Table
    changes: tuple[Change, ...]


@dataclass(frozen=True, slots=True)
class ReplaceEnum:
    """Recreate an enum type whose values are removed or reordered.

    ``columns`` lists, per table, the existing columns that keep using the type, in their
    target form, so they can be converted to the new type.
    """

    old: EnumType
    new: EnumType
    columns: tuple[tuple[str, Column], ...]


Operation: TypeAlias = Change | RebuildTable | ReplaceEnum


def describe_operation(operation: Operation) -> str:
    """Describe an operation in one line."""
    match operation:
        case RebuildTable(old, _, _):
            return f"rebuild table {old.name}"
        case ReplaceEnum(old, new, _):
            values = ", ".join(repr(value) for value in new.values)
            return f"recreate enum type {old.name} with values ({values})"
        case _:
            return describe(operation)
