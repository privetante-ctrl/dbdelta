"""SQLite table rebuilds."""

from collections.abc import Iterator, Sequence

from dbdelta.dialects import name_key
from dbdelta.dialects.sqlite import can_add_column
from dbdelta.diff import (
    AddColumn,
    AddIndex,
    Change,
    ColumnChange,
    ConstraintChange,
    DropColumn,
    DropIndex,
)
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding, Level
from dbdelta.risk.registry import rule
from dbdelta.risk.rules._helpers import rows_note


@rule("sqlite-rebuild", "SQLite rebuilds a table for any change ALTER TABLE cannot make.")
def sqlite_rebuild(changes: Sequence[Change], context: RiskContext) -> Iterator[Finding]:
    if context.dialect.traits.alters_table_definitions:
        return
    by_table: dict[str, tuple[str, list[Change]]] = {}
    for change in changes:
        if isinstance(change, ColumnChange | ConstraintChange):
            key = name_key(change.table, context.dialect)
            by_table.setdefault(key, (change.table, []))[1].append(change)
    for table, table_changes in by_table.values():
        # Mirrors the planner's choice of which tables to rebuild.
        in_place = all(_alters_in_place(change) for change in table_changes)
        if in_place and not _drops_every_column(table, table_changes, context):
            continue
        yield Finding(
            "sqlite-rebuild",
            Level.INFO if context.is_empty(table) else Level.WARNING,
            f"table {table}",
            f"SQLite cannot make these changes to {table} in place, so the table is rebuilt: "
            f"a new table is created, every row{rows_note(context, table)} is copied, the old "
            "table is dropped and the new one renamed. Writes to the database wait meanwhile, "
            "a full copy of the table needs free space, and triggers on the table are dropped "
            "and not recreated.",
            "Back up the database and run the migration while it is idle; recreate the "
            "table's triggers afterwards if it has any.",
            tuple(table_changes),
        )


def _alters_in_place(change: Change) -> bool:
    if isinstance(change, AddColumn):
        return can_add_column(change.column)
    return isinstance(change, DropColumn | AddIndex | DropIndex)


def _drops_every_column(table: str, changes: Sequence[Change], context: RiskContext) -> bool:
    """SQLite cannot drop a table's last column, so dropping them all rebuilds the table."""
    key = name_key(table, context.dialect)
    old = next((t for t in context.source.tables if name_key(t.name, context.dialect) == key), None)
    dropped = {
        name_key(change.column.name, context.dialect)
        for change in changes
        if isinstance(change, DropColumn)
    }
    return old is not None and dropped >= {
        name_key(column.name, context.dialect) for column in old.columns
    }
