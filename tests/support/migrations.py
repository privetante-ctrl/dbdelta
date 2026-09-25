"""Facts about a migration that the round-trip tests check against a real database."""

from collections.abc import Sequence

from dbdelta.dialects import Dialect, name_key
from dbdelta.diff import Change, RenameTable
from dbdelta.model import Schema


def surviving_tables(
    changes: Sequence[Change], source: Schema, target: Schema, dialect: Dialect
) -> list[tuple[str, str]]:
    """Tables of ``source`` that still exist after the migration: (old name, new name).

    Their rows must survive the migration, renamed tables included.
    """
    renamed = {
        name_key(change.table, dialect): change.new_name
        for change in changes
        if isinstance(change, RenameTable)
    }
    in_target = {name_key(table.name, dialect) for table in target.tables}
    surviving = []
    for table in source.tables:
        new_name = renamed.get(name_key(table.name, dialect), table.name)
        if name_key(new_name, dialect) in in_target:
            surviving.append((table.name, new_name))
    return surviving
