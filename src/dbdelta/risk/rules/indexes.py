"""Index builds that block writes."""

from dbdelta.dialects.postgresql import backs_foreign_key
from dbdelta.diff import AddIndex, Change
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding
from dbdelta.risk.registry import change_rule
from dbdelta.risk.rules._helpers import is_postgresql, lock_level


@change_rule("index-lock", "CREATE INDEX blocks writes to the table until it is built.")
def index_lock(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AddIndex) or not is_postgresql(context):
        return None
    table, index = change.table, change.index
    backs_key = backs_foreign_key(context.target, table, index)
    if context.concurrent_indexes and not backs_key:
        return None
    name = index.name or "the new index"
    if context.concurrent_indexes:
        recommendation = (
            f"{name} stays inside the transaction because a foreign key depends on it. Build "
            "it with CREATE UNIQUE INDEX CONCURRENTLY in a separate step before this migration."
        )
    else:
        recommendation = (
            "Run with --concurrent-indexes to build it with CREATE INDEX CONCURRENTLY outside "
            "the transaction: it takes longer but does not block writes."
        )
    return Finding(
        "index-lock",
        lock_level(context, table),
        f"index {name} on {table}",
        f"Building {name} blocks inserts, updates and deletes on {table} (SHARE lock) until "
        "the whole table has been indexed.",
        recommendation,
        (change,),
    )
