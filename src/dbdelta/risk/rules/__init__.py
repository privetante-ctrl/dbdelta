"""The built-in risk rules. Importing this package registers them."""

from dbdelta.risk.rules import columns, constraints, data_loss, indexes, renames, sqlite, types

__all__ = ["columns", "constraints", "data_loss", "indexes", "renames", "sqlite", "types"]
