"""Changes that delete data."""

from dbdelta.dialects.quoting import quote_identifier, quote_literal
from dbdelta.diff import AlterEnum, Change, DropColumn, DropTable
from dbdelta.model import Column
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding, Level
from dbdelta.risk.registry import change_rule
from dbdelta.risk.rules._helpers import LOCK_BLOCKS_ALL, column, rows_note


@change_rule("drop-table", "Dropping a table deletes all of its rows.")
def drop_table(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, DropTable):
        return None
    name = change.table.name
    if context.is_empty(name):
        return Finding(
            "drop-table",
            Level.INFO,
            f"table {name}",
            f"Table {name} is dropped; it holds no rows.",
            "No data is lost.",
            (change,),
        )
    return Finding(
        "drop-table",
        Level.DANGER,
        f"table {name}",
        f"Dropping {name} permanently deletes all of its rows{rows_note(context, name)}.",
        "Back the data up first, for example with CREATE TABLE ... AS SELECT, or stop using "
        "the table and drop it in a later release once nothing reads it.",
        (change,),
        check_sql=f"SELECT count(*) FROM {quote_identifier(name)}",
    )


@change_rule("drop-column", "Dropping a column deletes its values in every row.")
def drop_column(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, DropColumn):
        return None
    table, name = change.table, change.column.name
    subject = f"{table}.{name}"
    if context.is_empty(table):
        return Finding(
            "drop-column",
            Level.INFO,
            subject,
            f"Column {subject} is dropped; its table holds no rows.",
            "No data is lost.",
            (change,),
        )
    return Finding(
        "drop-column",
        Level.DANGER,
        subject,
        f"Dropping {subject} permanently deletes its value in every row"
        f"{rows_note(context, table)}.",
        "Stop reading and writing the column in the application and deploy that first, back "
        "the values up, then drop the column in a later migration (expand and contract).",
        (change,),
        check_sql=(
            f"SELECT count(*) FROM {quote_identifier(table)} "
            f"WHERE {column(table, name)} IS NOT NULL"
        ),
    )


@change_rule("enum-values", "Removing or reordering enum values affects existing rows.")
def enum_values(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AlterEnum):
        return None
    removed = [value for value in change.old.values if value not in change.new.values]
    kept_order = [value for value in change.old.values if value in change.new.values]
    reordered = kept_order != [value for value in change.new.values if value in kept_order]
    if not removed and not reordered:
        return None
    name = change.old.name
    recreate = (
        f"PostgreSQL cannot remove or reorder enum values, so the type is recreated and every "
        f"column using it is converted, rewriting those tables under {LOCK_BLOCKS_ALL}."
    )
    if not removed:
        return Finding(
            "enum-values",
            Level.WARNING,
            f"enum type {name}",
            f"Reordering the values of {name} changes how they sort and compare. {recreate}",
            "Only reorder values when queries do not depend on their order; appending new "
            "values instead is done in place.",
            (change,),
        )
    values = ", ".join(quote_literal(value) for value in removed)
    checks = [
        _rows_using(table.name, col, values)
        for table in context.source.tables
        for col in table.columns
        if col.type.name == name
    ]
    removal = f"Value {values} is" if len(removed) == 1 else f"Values {values} are"
    return Finding(
        "enum-values",
        Level.DANGER,
        f"enum type {name}",
        f"{removal} removed from {name}; rows that still hold them make the conversion fail. "
        f"{recreate}",
        "Update or delete the rows that use the removed values before migrating.",
        (change,),
        check_sql=";\n".join(checks) or None,
    )


def _rows_using(table: str, col: Column, values: str) -> str:
    reference = column(table, col.name)
    if col.type.is_array:
        condition = f"{reference}::text[] && ARRAY[{values}]"
    else:
        condition = f"{reference}::text IN ({values})"
    return f"SELECT count(*) FROM {quote_identifier(table)} WHERE {condition}"
