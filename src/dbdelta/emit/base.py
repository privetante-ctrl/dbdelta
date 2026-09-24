"""The emitter interface and the SQL that every dialect writes the same way."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from dbdelta.dialects import Dialect
from dbdelta.emit.quoting import quote_identifier, quote_qualified
from dbdelta.emit.script import Script
from dbdelta.model import (
    CheckConstraint,
    Column,
    DataType,
    ForeignKey,
    Index,
    PrimaryKey,
    ReferentialAction,
    Table,
    UniqueConstraint,
)
from dbdelta.plan import MigrationPlan


@dataclass(frozen=True, slots=True)
class EmitOptions:
    """Choices about how to write a migration that do not change its result."""

    concurrent_indexes: bool = False
    """Build and drop indexes of existing tables without blocking writes (PostgreSQL).

    Such statements use CONCURRENTLY and therefore run outside the migration transaction.
    """


class Emitter(ABC):
    """Writes the SQL of a migration plan for one dialect."""

    dialect: ClassVar[Dialect]

    def emit(self, plan: MigrationPlan, options: EmitOptions | None = None) -> Script:
        """Render ``plan`` as a script of SQL statements."""
        if plan.dialect is not self.dialect:
            raise ValueError(f"cannot write a {plan.dialect} migration as {self.dialect} SQL")
        return self._emit(plan, options or EmitOptions())

    @abstractmethod
    def _emit(self, plan: MigrationPlan, options: EmitOptions) -> Script: ...

    @abstractmethod
    def type_sql(self, data_type: DataType) -> str:
        """Spell a canonical type in this dialect."""

    @abstractmethod
    def column_sql(self, column: Column) -> str:
        """Column definition as used in CREATE TABLE and ADD COLUMN."""

    @abstractmethod
    def index_name(self, table: str, index: Index) -> str:
        """Name of an index, including the one the database chooses for an unnamed index."""

    def create_table(self, table: Table, name: str | None = None) -> str:
        """``CREATE TABLE`` with columns and constraints; indexes are separate statements."""
        items = [self.column_sql(column) for column in table.columns]
        items += self.table_constraints(table)
        body = ",\n    ".join(items)
        return f"CREATE TABLE {quote_identifier(name or table.name)} (\n    {body}\n)"

    def table_constraints(self, table: Table, *, primary_key: bool = True) -> list[str]:
        """Table-level constraint clauses; ``primary_key=False`` leaves the key out."""
        items = []
        if primary_key and table.primary_key is not None:
            items.append(self.primary_key_sql(table.primary_key))
        items += [self.unique_sql(unique) for unique in table.unique_constraints]
        items += [self.check_sql(check) for check in table.check_constraints]
        items += [self.foreign_key_sql(fk) for fk in table.foreign_keys]
        return items

    def primary_key_sql(self, key: PrimaryKey) -> str:
        return f"{_constraint(key.name)}PRIMARY KEY ({_columns(key.columns)})"

    def unique_sql(self, unique: UniqueConstraint) -> str:
        return f"{_constraint(unique.name)}UNIQUE ({_columns(unique.columns)})"

    def check_sql(self, check: CheckConstraint) -> str:
        return f"{_constraint(check.name)}CHECK ({check.expression.sql})"

    def foreign_key_sql(self, fk: ForeignKey) -> str:
        text = (
            f"{_constraint(fk.name)}FOREIGN KEY ({_columns(fk.columns)}) "
            f"REFERENCES {quote_qualified(fk.ref_table)} ({_columns(fk.ref_columns)})"
        )
        if fk.on_delete is not ReferentialAction.NO_ACTION:
            text += f" ON DELETE {fk.on_delete}"
        if fk.on_update is not ReferentialAction.NO_ACTION:
            text += f" ON UPDATE {fk.on_update}"
        return text

    def create_index(self, table: str, index: Index, *, concurrently: bool = False) -> str:
        unique = "UNIQUE " if index.unique else ""
        mode = "CONCURRENTLY " if concurrently else ""
        name = f"{quote_identifier(self.index_name(table, index))} "
        method = f" USING {index.method}" if index.method is not None else ""
        keys = ", ".join(
            (
                quote_identifier(element.key)
                if isinstance(element.key, str)
                # Index keys that are expressions must be parenthesized in both dialects.
                else f"({element.key.sql})"
            )
            + (" DESC" if element.descending else "")
            for element in index.elements
        )
        where = f" WHERE {index.where.sql}" if index.where is not None else ""
        return (
            f"CREATE {unique}INDEX {mode}{name}ON {quote_identifier(table)}{method} ({keys}){where}"
        )


def index_key_names(index: Index) -> list[str]:
    """Column names PostgreSQL and dbdelta derive index names from.

    Expressions are named after their outermost function, or ``expr``, and repeated names get
    a number, as PostgreSQL's ``ChooseIndexColumnNames`` does.
    """
    names: list[str] = []
    for element in index.elements:
        if isinstance(element.key, str):
            name = element.key
        else:
            head = element.key.sql.split("(", 1)[0]
            name = head.lower() if head.isidentifier() else "expr"
        candidate, number = name, 0
        while candidate in names:
            number += 1
            candidate = f"{name}{number}"
        names.append(candidate)
    return names


def _constraint(name: str | None) -> str:
    return f"CONSTRAINT {quote_identifier(name)} " if name is not None else ""


def _columns(names: tuple[str, ...]) -> str:
    return ", ".join(quote_identifier(name) for name in names)
