"""Immutable description of tables, constraints, indexes and enum types.

Every collection whose order carries no meaning (tables, constraints, indexes, enum types)
is sorted on construction, so two schemas describing the same database compare equal no
matter in which order their objects were declared. Table columns keep their declaration
order because it is visible to applications (``SELECT *``) and needed to emit ``CREATE TABLE``.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from dbdelta.model.types import DataType


class ReferentialAction(StrEnum):
    """Action taken on referencing rows when a referenced row is deleted or updated."""

    NO_ACTION = "NO ACTION"
    RESTRICT = "RESTRICT"
    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    SET_DEFAULT = "SET DEFAULT"


class Identity(StrEnum):
    """How the database generates values for a column.

    ``ALWAYS`` and ``BY_DEFAULT`` are PostgreSQL identity columns, ``SERIAL`` is a
    PostgreSQL ``serial``-family column, and ``AUTOINCREMENT`` is SQLite's keyword that
    forbids reusing the rowids of deleted rows.
    """

    ALWAYS = "always"
    BY_DEFAULT = "by default"
    SERIAL = "serial"
    AUTOINCREMENT = "autoincrement"


@dataclass(frozen=True, slots=True)
class Expression:
    """A SQL expression in canonical form, such as a CHECK condition or an index key.

    ``columns`` holds the table columns the expression reads. It is derived from ``sql``
    and is therefore ignored when comparing expressions.
    """

    sql: str
    columns: frozenset[str] = field(default=frozenset(), compare=False)

    def __str__(self) -> str:
        return self.sql


@dataclass(frozen=True, slots=True)
class Column:
    """A table column. ``default`` is a canonical SQL expression, not a Python value."""

    name: str
    type: DataType
    nullable: bool = True
    default: str | None = None
    identity: Identity | None = None


@dataclass(frozen=True, slots=True)
class PrimaryKey:
    """A primary key. ``name`` is ``None`` when the database chose it."""

    columns: tuple[str, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        _check_column_list(self.columns, "primary key")


@dataclass(frozen=True, slots=True)
class ForeignKey:
    """A foreign key from ``columns`` to ``ref_columns`` of ``ref_table``."""

    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]
    on_delete: ReferentialAction = ReferentialAction.NO_ACTION
    on_update: ReferentialAction = ReferentialAction.NO_ACTION
    name: str | None = None

    def __post_init__(self) -> None:
        _check_column_list(self.columns, "foreign key")
        if len(self.columns) != len(self.ref_columns):
            raise ValueError(
                f"foreign key {self.columns} references {len(self.ref_columns)} "
                f"column(s) of {self.ref_table!r}, expected {len(self.columns)}"
            )


@dataclass(frozen=True, slots=True)
class UniqueConstraint:
    """A UNIQUE constraint (as opposed to a unique index, see :class:`Index`)."""

    columns: tuple[str, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        _check_column_list(self.columns, "unique constraint")


@dataclass(frozen=True, slots=True)
class CheckConstraint:
    """A CHECK constraint, whether it was declared on a column or on the table."""

    expression: Expression
    name: str | None = None


@dataclass(frozen=True, slots=True)
class IndexElement:
    """One key of an index: a plain column name or an expression."""

    key: str | Expression
    descending: bool = False

    @property
    def columns(self) -> frozenset[str]:
        """Columns this key reads."""
        return frozenset({self.key}) if isinstance(self.key, str) else self.key.columns


@dataclass(frozen=True, slots=True)
class Index:
    """A secondary index.

    ``name`` is ``None`` when the database chose it, ``where`` is the predicate of a partial
    index and ``method`` is the PostgreSQL access method, ``None`` meaning the default btree.
    """

    name: str | None
    elements: tuple[IndexElement, ...]
    unique: bool = False
    where: Expression | None = None
    method: str | None = None

    def __post_init__(self) -> None:
        if not self.elements:
            raise ValueError(f"index {self.name!r} has no keys")

    @property
    def columns(self) -> frozenset[str]:
        """Columns read by the index keys and by its predicate."""
        keys = frozenset().union(*(element.columns for element in self.elements))
        return keys | self.where.columns if self.where is not None else keys


@dataclass(frozen=True, slots=True)
class Table:
    """A table with its columns, constraints and indexes."""

    name: str
    columns: tuple[Column, ...]
    primary_key: PrimaryKey | None = None
    foreign_keys: tuple[ForeignKey, ...] = ()
    unique_constraints: tuple[UniqueConstraint, ...] = ()
    check_constraints: tuple[CheckConstraint, ...] = ()
    indexes: tuple[Index, ...] = ()

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError(f"table {self.name!r} has no columns")
        _check_unique_names((column.name for column in self.columns), f"table {self.name!r}")
        self._check_references()
        _set(self, "foreign_keys", tuple(sorted(self.foreign_keys, key=_foreign_key_order)))
        _set(
            self,
            "unique_constraints",
            tuple(sorted(self.unique_constraints, key=lambda u: (u.columns, u.name or ""))),
        )
        _set(
            self,
            "check_constraints",
            tuple(sorted(self.check_constraints, key=lambda c: (c.expression.sql, c.name or ""))),
        )
        _set(self, "indexes", tuple(sorted(self.indexes, key=_index_order)))

    @property
    def column_names(self) -> tuple[str, ...]:
        """Column names in declaration order."""
        return tuple(column.name for column in self.columns)

    def column(self, name: str) -> Column | None:
        """Return the column called ``name``, if any."""
        return next((column for column in self.columns if column.name == name), None)

    def _check_references(self) -> None:
        known = set(self.column_names)
        referenced: list[tuple[str, Iterable[str]]] = [
            ("foreign key", fk.columns) for fk in self.foreign_keys
        ]
        if self.primary_key is not None:
            referenced.append(("primary key", self.primary_key.columns))
        referenced += [("unique constraint", u.columns) for u in self.unique_constraints]
        referenced += [
            (f"index {index.name!r}", (e.key for e in index.elements if isinstance(e.key, str)))
            for index in self.indexes
        ]
        for owner, columns in referenced:
            missing = sorted(set(columns) - known)
            if missing:
                raise ValueError(
                    f"{owner} of table {self.name!r} references unknown column(s) {missing}"
                )


@dataclass(frozen=True, slots=True)
class EnumType:
    """A PostgreSQL enum type. The order of ``values`` is significant."""

    name: str
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError(f"enum type {self.name!r} has no values")
        _check_unique_names(self.values, f"enum type {self.name!r}")


@dataclass(frozen=True, slots=True)
class Schema:
    """A database schema: the unit that dbdelta loads, compares and migrates."""

    tables: tuple[Table, ...] = ()
    enums: tuple[EnumType, ...] = ()

    def __post_init__(self) -> None:
        _check_unique_names((table.name for table in self.tables), "schema tables")
        _check_unique_names((enum.name for enum in self.enums), "schema enum types")
        _set(self, "tables", tuple(sorted(self.tables, key=lambda table: table.name)))
        _set(self, "enums", tuple(sorted(self.enums, key=lambda enum: enum.name)))

    def table(self, name: str) -> Table | None:
        """Return the table called ``name``, if any."""
        return next((table for table in self.tables if table.name == name), None)

    def enum(self, name: str) -> EnumType | None:
        """Return the enum type called ``name``, if any."""
        return next((enum for enum in self.enums if enum.name == name), None)


def _set(instance: object, name: str, value: object) -> None:
    # Frozen dataclasses may only be canonicalized in __post_init__ through object.__setattr__.
    object.__setattr__(instance, name, value)


def _check_column_list(columns: tuple[str, ...], owner: str) -> None:
    if not columns:
        raise ValueError(f"{owner} has no columns")
    _check_unique_names(columns, owner)


def _check_unique_names(names: Iterable[str], owner: str) -> None:
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise ValueError(f"{owner} lists {duplicates} more than once")


def _foreign_key_order(fk: ForeignKey) -> tuple[tuple[str, ...], str, tuple[str, ...], str]:
    return (fk.columns, fk.ref_table, fk.ref_columns, fk.name or "")


def _index_order(index: Index) -> tuple[str, tuple[tuple[str, bool], ...], str]:
    keys = tuple((str(element.key), element.descending) for element in index.elements)
    return (index.name or "", keys, index.where.sql if index.where is not None else "")
