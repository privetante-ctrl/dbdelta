"""Facts about each supported SQL dialect, shared by loaders, risk rules and emitters.

Adding a dialect starts here: this package describes what the database can do, while
``loaders`` and ``emit`` hold the code that reads and writes its SQL.
"""

from enum import StrEnum


class Dialect(StrEnum):
    """A supported database dialect. Values match the SQLAlchemy URL scheme."""

    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"
