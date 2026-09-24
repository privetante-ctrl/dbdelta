"""Facts about each supported SQL dialect, shared by loaders, the diff, the planner and emitters.

Adding a dialect starts here: this package describes how the database behaves, while
``loaders`` and ``emit`` hold the code that reads and writes its SQL.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class DialectTraits:
    """Behaviour of a dialect that the dialect-neutral layers depend on."""

    case_sensitive_names: bool
    """Whether ``Users`` and ``users`` name different objects."""

    checks_foreign_keys_in_ddl: bool
    """Whether DDL enforces foreign key dependencies.

    If so, a foreign key can only be created once its referenced table and key exist, and
    that key cannot be dropped while the foreign key uses it.
    """


class Dialect(StrEnum):
    """A supported database dialect. Values match the SQLAlchemy URL scheme."""

    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"

    @property
    def traits(self) -> DialectTraits:
        return _TRAITS[self]


_TRAITS = {
    # Quoted names keep their case; unquoted ones are folded by the loaders already.
    Dialect.POSTGRESQL: DialectTraits(case_sensitive_names=True, checks_foreign_keys_in_ddl=True),
    # SQLite resolves foreign keys only when rows are written, so cycles need no special care.
    Dialect.SQLITE: DialectTraits(case_sensitive_names=False, checks_foreign_keys_in_ddl=False),
}

_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def ascii_lower(name: str) -> str:
    """Lower-case ASCII letters only, the way both PostgreSQL and SQLite fold names."""
    return name.translate(_ASCII_LOWER)


def name_key(name: str, dialect: Dialect) -> str:
    """Key under which ``dialect`` considers two names to denote the same object."""
    return name if dialect.traits.case_sensitive_names else ascii_lower(name)
