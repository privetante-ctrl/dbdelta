"""SQLite behaviour that the planner and the emitter rely on."""

import re

from dbdelta.model import Column

# Defaults ALTER TABLE ADD COLUMN accepts: literals only, no CURRENT_* keywords and no
# expressions, which would have to be computed for the rows already in the table.
_CONSTANT_DEFAULT = re.compile(
    r"NULL|TRUE|FALSE|-?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?|'([^']|'')*'|[xX]'[0-9a-fA-F]*'"
)


def is_constant(default: str) -> bool:
    """Tell whether a canonical default is a literal rather than an expression."""
    return _CONSTANT_DEFAULT.fullmatch(default) is not None


def can_add_column(column: Column) -> bool:
    """Tell whether ``ALTER TABLE ... ADD COLUMN`` can add ``column`` to a populated table."""
    if column.identity is not None:
        return False
    if column.default is None:
        return column.nullable
    return is_constant(column.default)
