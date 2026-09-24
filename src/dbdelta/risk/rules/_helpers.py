"""Shared wording and SQL fragments for risk rules."""

from collections.abc import Iterable

from dbdelta.dialects import Dialect, name_key
from dbdelta.dialects.quoting import quote_identifier
from dbdelta.model import Column, Schema, Table
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Level

LOCK_BLOCKS_ALL = "an ACCESS EXCLUSIVE lock that blocks reads and writes"


def column(table: str, name: str) -> str:
    """Quoted ``table.column`` reference for check queries."""
    return f"{quote_identifier(table)}.{quote_identifier(name)}"


def rows_note(context: RiskContext, table: str) -> str:
    """`` (about 1,200 rows)`` when the size of ``table`` is known."""
    rows = context.rows(table)
    return f" (about {rows:,} rows)" if rows is not None else ""


def lock_level(context: RiskContext, table: str) -> Level:
    """Locking only matters on tables that may be large."""
    return Level.INFO if context.is_small(table) else Level.WARNING


def is_postgresql(context: RiskContext) -> bool:
    return context.dialect is Dialect.POSTGRESQL


def columns_exist(context: RiskContext, table: str, names: Iterable[str]) -> bool:
    """Whether every column already exists, so a check query can read it before migrating."""
    return not new_columns(context, table, names)


def new_columns(context: RiskContext, table: str, names: Iterable[str]) -> list[Column]:
    """The columns among ``names`` that the migration adds to ``table``, as they will be."""
    old, new = _table(context.source, table, context), _table(context.target, table, context)
    existing = {name_key(found.name, context.dialect) for found in old.columns} if old else set()
    return [
        found
        for found in (new.columns if new else ())
        if name_key(found.name, context.dialect) not in existing
        and name_key(found.name, context.dialect)
        in {name_key(name, context.dialect) for name in names}
    ]


def _table(schema: Schema, name: str, context: RiskContext) -> Table | None:
    key = name_key(name, context.dialect)
    return next(
        (found for found in schema.tables if name_key(found.name, context.dialect) == key), None
    )
