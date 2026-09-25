"""Everything a risk rule may look at besides the changes themselves."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from dbdelta.dialects import Dialect, name_key
from dbdelta.diff import Change, RenameTable, apply_renames
from dbdelta.model import Schema

DEFAULT_LARGE_TABLE_ROWS = 100_000


@dataclass(frozen=True)
class RiskContext:
    """The migration being assessed and what is known about the data.

    ``row_estimates`` maps table names to their approximate row counts when the source is a
    live database. A table without an estimate is treated as possibly large and possibly
    holding data, so the rules err on the side of warning.
    """

    dialect: Dialect
    source: Schema
    target: Schema
    row_estimates: Mapping[str, int] = field(default_factory=dict)
    large_table_rows: int = DEFAULT_LARGE_TABLE_ROWS
    concurrent_indexes: bool = False

    def after_renames(self, changes: Iterable[Change]) -> "RiskContext":
        """This context with the source as it is once the renames among ``changes`` ran.

        Changes after a rename use the new names, so rules look tables up by those.
        """
        changes = list(changes)
        estimates = dict(self.row_estimates)
        for change in changes:
            rows = self.rows(change.table) if isinstance(change, RenameTable) else None
            if isinstance(change, RenameTable) and rows is not None:
                estimates[change.new_name] = rows
        source = apply_renames(self.source, changes, self.dialect)
        return replace(self, source=source, row_estimates=estimates)

    def rows(self, table: str) -> int | None:
        """Estimated row count of ``table``, or ``None`` if unknown."""
        key = name_key(table, self.dialect)
        return next(
            (
                rows
                for name, rows in self.row_estimates.items()
                if name_key(name, self.dialect) == key
            ),
            None,
        )

    def is_empty(self, table: str) -> bool:
        """Whether ``table`` is known to hold no rows."""
        return self.rows(table) == 0

    def is_small(self, table: str) -> bool:
        """Whether ``table`` is known to be smaller than the large table threshold."""
        rows = self.rows(table)
        return rows is not None and rows < self.large_table_rows
