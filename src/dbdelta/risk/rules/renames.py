"""Renames, and drops and adds that may have been meant as renames."""

from collections.abc import Iterator, Sequence

from dbdelta.diff import Change, RenameColumn, RenameTable, possible_renames
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding, Level
from dbdelta.risk.registry import change_rule, rule


@change_rule("rename", "Renaming breaks code and SQL that still use the old name.")
def rename(change: Change, context: RiskContext) -> Finding | None:  # noqa: ARG001
    if isinstance(change, RenameTable):
        what, old, new = "table", change.table, change.new_name
        safer = (
            "Deploy application code that accepts both names first. In PostgreSQL, a view "
            "under the old name can serve old readers until they are gone."
        )
    elif isinstance(change, RenameColumn):
        what, old, new = "column", f"{change.table}.{change.column}", change.new_name
        safer = (
            "Deploy application code that accepts both names first, or rename in steps: add "
            "the new column, write to both, backfill, switch reads, then drop the old one."
        )
    else:
        return None
    return Finding(
        "rename",
        Level.WARNING,
        f"{what} {old}",
        f"Renaming {what} {old} to {new} keeps its data, but application code, views, "
        "functions and triggers that still use the old name fail. The database updates "
        "keys, indexes and foreign keys itself.",
        safer,
        (change,),
    )


@rule("possible-rename", "A dropped and an added object of the same shape may be a rename.")
def possible_rename(changes: Sequence[Change], context: RiskContext) -> Iterator[Finding]:  # noqa: ARG001
    for candidate in possible_renames(changes):
        renamed = candidate.rename
        if isinstance(renamed, RenameTable):
            what, old, new = "table", renamed.table, renamed.new_name
            loss = "all of its rows"
        else:
            what, old, new = "column", f"{renamed.table}.{renamed.column}", renamed.new_name
            loss = "its values"
        yield Finding(
            "possible-rename",
            Level.WARNING,
            f"{what} {old}",
            f"{what.capitalize()} {old} is dropped and {new} is added with the same shape; "
            f"this looks like a rename (confidence {candidate.confidence:.0%}). As written, "
            f"the migration deletes {loss} instead of keeping them.",
            "If it is a rename, run with --detect-renames to generate a RENAME, which keeps "
            "the data. Otherwise, make sure the data is no longer needed.",
            (candidate.dropped, candidate.added),
        )
