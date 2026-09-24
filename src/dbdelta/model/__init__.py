"""Immutable, dialect-neutral description of a database schema.

This is the bottom layer: it must not depend on any other dbdelta package,
nor on sqlglot or SQLAlchemy.
"""

from dbdelta.model.schema import (
    CheckConstraint,
    Column,
    EnumType,
    Expression,
    ForeignKey,
    Identity,
    Index,
    IndexElement,
    PrimaryKey,
    ReferentialAction,
    Schema,
    Table,
    UniqueConstraint,
)
from dbdelta.model.types import DataType

__all__ = [
    "CheckConstraint",
    "Column",
    "DataType",
    "EnumType",
    "Expression",
    "ForeignKey",
    "Identity",
    "Index",
    "IndexElement",
    "PrimaryKey",
    "ReferentialAction",
    "Schema",
    "Table",
    "UniqueConstraint",
]
