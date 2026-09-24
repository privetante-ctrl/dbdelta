"""Typed changes that turn one schema into another.

Each change is a small immutable record of one difference. Changes inside a table carry the
table name as it exists in the source schema, because that is the name the migration has
to address. ``Change`` is the union of all of them, so consumers can match exhaustively.
"""

from dataclasses import dataclass
from typing import TypeAlias

from dbdelta.model import (
    CheckConstraint,
    Column,
    DataType,
    EnumType,
    ForeignKey,
    Identity,
    Index,
    PrimaryKey,
    Table,
    UniqueConstraint,
)


@dataclass(frozen=True, slots=True)
class AddEnum:
    enum: EnumType


@dataclass(frozen=True, slots=True)
class DropEnum:
    enum: EnumType


@dataclass(frozen=True, slots=True)
class AlterEnum:
    """The values of an enum type changed. Only appending values is always safe."""

    old: EnumType
    new: EnumType


@dataclass(frozen=True, slots=True)
class AddTable:
    """Create a table with its constraints and indexes."""

    table: Table


@dataclass(frozen=True, slots=True)
class DropTable:
    """Drop a table together with its constraints and indexes."""

    table: Table


@dataclass(frozen=True, slots=True)
class AddColumn:
    table: str
    column: Column


@dataclass(frozen=True, slots=True)
class DropColumn:
    table: str
    column: Column


@dataclass(frozen=True, slots=True)
class AlterColumnType:
    table: str
    column: str
    old: DataType
    new: DataType


@dataclass(frozen=True, slots=True)
class SetNotNull:
    table: str
    column: str


@dataclass(frozen=True, slots=True)
class DropNotNull:
    table: str
    column: str


@dataclass(frozen=True, slots=True)
class SetDefault:
    """Add a default or replace an existing one (``old`` is ``None`` if there was none)."""

    table: str
    column: str
    old: str | None
    new: str


@dataclass(frozen=True, slots=True)
class DropDefault:
    table: str
    column: str
    old: str


@dataclass(frozen=True, slots=True)
class AlterIdentity:
    table: str
    column: str
    old: Identity | None
    new: Identity | None


@dataclass(frozen=True, slots=True)
class ReorderColumns:
    """Column order differs; only reported with strict column order checking."""

    table: str
    old: tuple[str, ...]
    new: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AddPrimaryKey:
    table: str
    primary_key: PrimaryKey


@dataclass(frozen=True, slots=True)
class DropPrimaryKey:
    table: str
    primary_key: PrimaryKey


@dataclass(frozen=True, slots=True)
class AddForeignKey:
    table: str
    foreign_key: ForeignKey


@dataclass(frozen=True, slots=True)
class DropForeignKey:
    table: str
    foreign_key: ForeignKey


@dataclass(frozen=True, slots=True)
class AddUnique:
    table: str
    constraint: UniqueConstraint


@dataclass(frozen=True, slots=True)
class DropUnique:
    table: str
    constraint: UniqueConstraint


@dataclass(frozen=True, slots=True)
class AddCheck:
    table: str
    constraint: CheckConstraint


@dataclass(frozen=True, slots=True)
class DropCheck:
    table: str
    constraint: CheckConstraint


@dataclass(frozen=True, slots=True)
class AddIndex:
    table: str
    index: Index


@dataclass(frozen=True, slots=True)
class DropIndex:
    table: str
    index: Index


ColumnChange: TypeAlias = (
    AddColumn
    | DropColumn
    | AlterColumnType
    | SetNotNull
    | DropNotNull
    | SetDefault
    | DropDefault
    | AlterIdentity
    | ReorderColumns
)

ConstraintChange: TypeAlias = (
    AddPrimaryKey
    | DropPrimaryKey
    | AddForeignKey
    | DropForeignKey
    | AddUnique
    | DropUnique
    | AddCheck
    | DropCheck
    | AddIndex
    | DropIndex
)

Change: TypeAlias = (
    AddEnum | DropEnum | AlterEnum | AddTable | DropTable | ColumnChange | ConstraintChange
)
