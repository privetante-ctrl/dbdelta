"""Constraints added to tables that already hold rows."""

from dbdelta.dialects.quoting import quote_identifier, quote_qualified
from dbdelta.diff import AddCheck, AddForeignKey, AddIndex, AddPrimaryKey, AddUnique, Change
from dbdelta.model import Expression, ForeignKey
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding, Level
from dbdelta.risk.registry import change_rule
from dbdelta.risk.rules._helpers import (
    LOCK_BLOCKS_ALL,
    columns_exist,
    is_postgresql,
    lock_level,
    new_columns,
)


@change_rule("unique-duplicates", "Existing duplicates make a new unique key fail.")
def unique_duplicates(change: Change, context: RiskContext) -> Finding | None:
    if isinstance(change, AddUnique | AddPrimaryKey):
        table = change.table
        constraint = change.constraint if isinstance(change, AddUnique) else change.primary_key
        keys: list[str | Expression] = list(constraint.columns)
        where: Expression | None = None
        kind = "primary key" if isinstance(change, AddPrimaryKey) else "unique constraint"
    elif isinstance(change, AddIndex) and change.index.unique:
        table = change.table
        keys = [element.key for element in change.index.elements]
        where = change.index.where
        kind = "unique index"
    else:
        return None
    if context.is_empty(table):
        return None
    added = new_columns(context, table, _read_columns(keys, where))
    if kind != "primary key" and any(
        column.default is None and column.identity is None for column in added
    ):
        # Existing rows get NULL in that column, and unique keys ignore rows with a NULL.
        return None
    rendered = [_key_sql(key) for key in keys]
    listed = ", ".join(rendered)
    named = ", ".join(str(key) for key in keys)
    filters = [f"{key} IS NOT NULL" for key in rendered]
    if where is not None:
        filters.append(f"({where.sql})")
    if is_postgresql(context) and kind != "unique index":
        recommendation = (
            "Remove the duplicates first. On a large table, build the index with CREATE UNIQUE "
            "INDEX CONCURRENTLY and attach it with ALTER TABLE ... ADD CONSTRAINT ... USING "
            "INDEX, which avoids blocking writes."
        )
    else:
        recommendation = "Remove the duplicates first."
    return Finding(
        "unique-duplicates",
        Level.WARNING,
        f"{kind} on {table} ({named})",
        f"Rows already in {table} may contain duplicates of ({named}), which make adding "
        f"the {kind} fail.",
        recommendation,
        (change,),
        check_sql=(
            f"SELECT {listed}, count(*) FROM {quote_identifier(table)} "
            f"WHERE {' AND '.join(filters)} GROUP BY {listed} HAVING count(*) > 1"
            if not added
            else None
        ),
    )


@change_rule("check-violations", "Existing rows may violate a new CHECK constraint.")
def check_violations(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AddCheck) or context.is_empty(change.table):
        return None
    table, condition = change.table, change.constraint.expression.sql
    if is_postgresql(context):
        locking = f" PostgreSQL checks every row while holding {LOCK_BLOCKS_ALL}."
        recommendation = (
            "Fix the violating rows first. On a large table, add the constraint with NOT VALID "
            "and run ALTER TABLE ... VALIDATE CONSTRAINT separately; validating does not block "
            "writes."
        )
    else:
        locking = ""
        recommendation = "Fix the violating rows first."
    return Finding(
        "check-violations",
        Level.WARNING,
        f"check on {table} ({condition})",
        f"Rows already in {table} may violate CHECK ({condition}), which makes the migration "
        f"fail.{locking}",
        recommendation,
        (change,),
        check_sql=(
            f"SELECT count(*) FROM {quote_identifier(table)} WHERE NOT ({condition})"
            if columns_exist(context, table, change.constraint.expression.columns)
            else None
        ),
    )


@change_rule("foreign-key", "Adding a foreign key checks every row and locks both tables.")
def foreign_key(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AddForeignKey) or context.is_empty(change.table):
        return None
    table, fk = change.table, change.foreign_key
    subject = f"foreign key {table} ({', '.join(fk.columns)}) -> {fk.ref_table}"
    # A referenced table or key the migration creates is empty when the key is added.
    parent_is_new = not columns_exist(context, fk.ref_table, fk.ref_columns)
    check_sql = None
    if columns_exist(context, table, fk.columns):
        check_sql = _with_keys(table, fk) if parent_is_new else _orphans(table, fk)
    empty_parent = (
        f" {fk.ref_table} ({', '.join(fk.ref_columns)}) is new and holds no rows yet, so no "
        "row has a match."
        if parent_is_new
        else ""
    )
    if not is_postgresql(context):
        return Finding(
            "foreign-key",
            Level.WARNING,
            subject,
            f"SQLite does not check existing rows of {table} when a foreign key is added. The "
            "migration runs PRAGMA foreign_key_check, which lists rows without a match but "
            f"does not stop the migration.{empty_parent}",
            "Delete or fix rows without a matching row before migrating.",
            (change,),
            check_sql=check_sql,
        )
    return Finding(
        "foreign-key",
        lock_level(context, table),
        subject,
        f"Adding the foreign key checks every row of {table} while holding SHARE ROW EXCLUSIVE "
        f"locks on {table} and {fk.ref_table}, which block writes to both; rows without a "
        f"match make the migration fail.{empty_parent}",
        "Add the constraint with NOT VALID, which only takes a brief lock, then run ALTER "
        "TABLE ... VALIDATE CONSTRAINT in a separate transaction; validating does not block "
        "writes.",
        (change,),
        check_sql=check_sql,
    )


def _read_columns(keys: list[str | Expression], where: Expression | None) -> set[str]:
    columns = {key for key in keys if isinstance(key, str)}
    columns.update(*(key.columns for key in keys if isinstance(key, Expression)))
    if where is not None:
        columns.update(where.columns)
    return columns


def _key_sql(key: str | Expression) -> str:
    return quote_identifier(key) if isinstance(key, str) else key.sql


def _with_keys(table: str, fk: ForeignKey) -> str:
    """Rows of ``table`` that need a match; all of them lack one when the parent is new."""
    present = " AND ".join(f"{quote_identifier(name)} IS NOT NULL" for name in fk.columns)
    return f"SELECT count(*) FROM {quote_identifier(table)} WHERE {present}"


def _orphans(table: str, fk: ForeignKey) -> str:
    """Rows of ``table`` whose key has no match; rows with a NULL key column are exempt."""
    present = " AND ".join(f"child.{quote_identifier(name)} IS NOT NULL" for name in fk.columns)
    matched = " AND ".join(
        f"parent.{quote_identifier(ref)} = child.{quote_identifier(name)}"
        for name, ref in zip(fk.columns, fk.ref_columns, strict=True)
    )
    return (
        f"SELECT count(*) FROM {quote_identifier(table)} AS child WHERE {present} "
        f"AND NOT EXISTS (SELECT 1 FROM {quote_qualified(fk.ref_table)} AS parent "
        f"WHERE {matched})"
    )
