"""What a risk rule reports."""

from dataclasses import dataclass
from enum import StrEnum

from dbdelta.diff import Change


class Level(StrEnum):
    """How dangerous a finding is, from least to most."""

    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"

    @property
    def severity(self) -> int:
        """Rank for ordering: higher is more dangerous."""
        return _SEVERITY[self]


_SEVERITY = {Level.INFO: 0, Level.WARNING: 1, Level.DANGER: 2}


@dataclass(frozen=True, slots=True)
class Finding:
    """One risk of a migration, with what to do about it.

    ``message`` says what can go wrong and why, ``recommendation`` gives a safer way to make
    the change, and ``check_sql``, when present, is a query to run before migrating that
    shows whether the data allows the change.
    """

    rule: str
    level: Level
    subject: str
    message: str
    recommendation: str
    changes: tuple[Change, ...]
    check_sql: str | None = None
