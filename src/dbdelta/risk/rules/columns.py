"""Adding columns and making columns NOT NULL on tables that already hold rows."""

from dbdelta.dialects.postgresql import has_volatile_default
from dbdelta.dialects.quoting import quote_identifier
from dbdelta.diff import AddColumn, Change, SetNotNull
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding, Level
from dbdelta.risk.registry import change_rule
from dbdelta.risk.rules._helpers import LOCK_BLOCKS_ALL, column, is_postgresql, lock_level


@change_rule(
    "add-not-null-column", "A NOT NULL column without a default cannot be added to a filled table."
)
def add_not_null_column(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AddColumn):
        return None
    added = change.column
    if added.nullable or added.default is not None or added.identity is not None:
        return None
    subject = f"{change.table}.{added.name}"
    fast_default = (
        " In PostgreSQL 11 and later, ADD COLUMN with a constant DEFAULT is instant."
        if is_postgresql(context)
        else ""
    )
    return Finding(
        "add-not-null-column",
        Level.INFO if context.is_empty(change.table) else Level.DANGER,
        subject,
        f"{subject} is added as NOT NULL without a default, which fails as soon as "
        f"{change.table} holds any row: existing rows would have no value.",
        "Add the column as nullable or with a DEFAULT, fill it for existing rows, then make "
        f"it NOT NULL in a later step.{fast_default}",
        (change,),
        check_sql=f"SELECT count(*) FROM {quote_identifier(change.table)}",
    )


@change_rule(
    "add-column-rewrite", "Adding a column whose value differs per row rewrites the table."
)
def add_column_rewrite(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AddColumn) or not is_postgresql(context):
        return None
    added = change.column
    if added.identity is not None:
        reason = "an identity column"
    elif added.default is not None and has_volatile_default(added.default):
        reason = f"a column whose default ({added.default}) differs from row to row"
    else:
        return None
    subject = f"{change.table}.{added.name}"
    return Finding(
        "add-column-rewrite",
        lock_level(context, change.table),
        subject,
        f"{subject} is {reason}, so PostgreSQL computes a value for every existing row and "
        f"rewrites the table while holding {LOCK_BLOCKS_ALL}.",
        "On a large table, add the column without a default, set the default for new rows "
        "separately and backfill existing rows in batches.",
        (change,),
    )


@change_rule("set-not-null", "Making a column NOT NULL fails if it holds NULLs.")
def set_not_null(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, SetNotNull) or context.is_empty(change.table):
        return None
    subject = f"{change.table}.{change.column}"
    if is_postgresql(context):
        message = (
            f"Making {subject} NOT NULL fails if any row holds NULL, and PostgreSQL checks "
            f"every row while holding {LOCK_BLOCKS_ALL}."
        )
        recommendation = (
            "Backfill the NULLs first. On a large table, add CHECK (column IS NOT NULL) NOT "
            "VALID, validate it in a separate transaction, then SET NOT NULL: PostgreSQL 12 "
            "and later use the validated constraint and skip the scan."
        )
    else:
        message = f"Making {subject} NOT NULL fails if any row holds NULL."
        recommendation = "Backfill the NULLs before migrating."
    return Finding(
        "set-not-null",
        Level.WARNING,
        subject,
        message,
        recommendation,
        (change,),
        check_sql=(
            f"SELECT count(*) FROM {quote_identifier(change.table)} "
            f"WHERE {column(change.table, change.column)} IS NULL"
        ),
    )
