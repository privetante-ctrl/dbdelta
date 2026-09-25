"""One-line, human-readable descriptions of changes."""

from typing import assert_never

from dbdelta.diff.changes import (
    AddCheck,
    AddColumn,
    AddEnum,
    AddForeignKey,
    AddIndex,
    AddPrimaryKey,
    AddTable,
    AddUnique,
    AlterColumnType,
    AlterEnum,
    AlterIdentity,
    Change,
    DropCheck,
    DropColumn,
    DropDefault,
    DropEnum,
    DropForeignKey,
    DropIndex,
    DropNotNull,
    DropPrimaryKey,
    DropTable,
    DropUnique,
    RenameColumn,
    RenameTable,
    ReorderColumns,
    SetDefault,
    SetNotNull,
)
from dbdelta.model import Column, ForeignKey, Index


def describe(change: Change) -> str:
    """Describe ``change`` in one line, for reports and logs."""
    match change:
        case AddEnum(enum):
            return f"create enum type {enum.name} ({_values(enum.values)})"
        case DropEnum(enum):
            return f"drop enum type {enum.name}"
        case AlterEnum(old, new):
            return (
                f"change values of enum type {old.name} "
                f"from ({_values(old.values)}) to ({_values(new.values)})"
            )
        case AddTable(table):
            return f"create table {table.name}"
        case DropTable(table):
            return f"drop table {table.name}"
        case RenameTable(table, new_name):
            return f"rename table {table} to {new_name}"
        case RenameColumn(table, column, new_name):
            return f"rename column {table}.{column} to {new_name}"
        case AddColumn(table, column):
            return f"add column {table}.{column_definition(column)}"
        case DropColumn(table, column):
            return f"drop column {table}.{column.name}"
        case AlterColumnType(table, column, old, new):
            return f"change type of {table}.{column} from {old} to {new}"
        case SetNotNull(table, column):
            return f"make {table}.{column} NOT NULL"
        case DropNotNull(table, column):
            return f"allow NULL in {table}.{column}"
        case SetDefault(table, column, _, new):
            return f"set default of {table}.{column} to {new}"
        case DropDefault(table, column, _):
            return f"drop default of {table}.{column}"
        case AlterIdentity(table, column, old, new):
            return f"change identity of {table}.{column} from {old or 'none'} to {new or 'none'}"
        case ReorderColumns(table, _, new):
            return f"reorder columns of {table} to ({', '.join(new)})"
        case AddPrimaryKey(table, key):
            return f"add primary key{_named(key.name)} on {table} ({', '.join(key.columns)})"
        case DropPrimaryKey(table, key):
            return f"drop primary key{_named(key.name)} on {table} ({', '.join(key.columns)})"
        case AddForeignKey(table, fk):
            return f"add foreign key{_named(fk.name)} {table} {foreign_key_definition(fk)}"
        case DropForeignKey(table, fk):
            return f"drop foreign key{_named(fk.name)} {table} {foreign_key_definition(fk)}"
        case AddUnique(table, unique):
            columns = ", ".join(unique.columns)
            return f"add unique constraint{_named(unique.name)} on {table} ({columns})"
        case DropUnique(table, unique):
            columns = ", ".join(unique.columns)
            return f"drop unique constraint{_named(unique.name)} on {table} ({columns})"
        case AddCheck(table, check):
            return f"add check constraint{_named(check.name)} on {table} ({check.expression})"
        case DropCheck(table, check):
            return f"drop check constraint{_named(check.name)} on {table} ({check.expression})"
        case AddIndex(table, index):
            return f"create {index_definition(table, index)}"
        case DropIndex(table, index):
            return f"drop {index_definition(table, index)}"
        case _:
            assert_never(change)


def column_definition(column: Column) -> str:
    """Render a column like ``email varchar(255) NOT NULL DEFAULT ''``."""
    parts = [column.name]
    if str(column.type):
        parts.append(str(column.type))
    if not column.nullable:
        parts.append("NOT NULL")
    if column.default is not None:
        parts.append(f"DEFAULT {column.default}")
    if column.identity is not None:
        parts.append(f"[{column.identity}]")
    return " ".join(parts)


def foreign_key_definition(fk: ForeignKey) -> str:
    """Render a foreign key like ``(org_id) -> orgs (id) ON DELETE CASCADE``."""
    text = f"({', '.join(fk.columns)}) -> {fk.ref_table} ({', '.join(fk.ref_columns)})"
    if fk.on_delete != "NO ACTION":
        text += f" ON DELETE {fk.on_delete}"
    if fk.on_update != "NO ACTION":
        text += f" ON UPDATE {fk.on_update}"
    return text


def index_definition(table: str, index: Index) -> str:
    """Render an index like ``unique index ix on users (lower(email)) where ...``."""
    keys = ", ".join(
        f"{element.key}{' DESC' if element.descending else ''}" for element in index.elements
    )
    text = f"{'unique ' if index.unique else ''}index{_named(index.name)} on {table}"
    if index.method is not None:
        text += f" using {index.method}"
    text += f" ({keys})"
    if index.where is not None:
        text += f" where {index.where}"
    return text


def _named(name: str | None) -> str:
    return f" {name}" if name is not None else ""


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(repr(value) for value in values)
