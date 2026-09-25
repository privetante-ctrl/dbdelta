"""Compute the changes that turn a source schema into a target schema."""

from collections.abc import Callable, Hashable, Iterator, Sequence
from typing import Protocol, TypeVar

from dbdelta.dialects import Dialect, name_key
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
    RenameChange,
    RenameColumn,
    RenameTable,
    ReorderColumns,
    SetDefault,
    SetNotNull,
)
from dbdelta.diff.renames import apply_renames, possible_renames
from dbdelta.model import (
    CheckConstraint,
    Column,
    EnumType,
    ForeignKey,
    Index,
    PrimaryKey,
    Schema,
    Table,
    UniqueConstraint,
)


class _Named(Protocol):
    @property
    def name(self) -> str | None: ...


_T = TypeVar("_T", bound=_Named)


def diff_schemas(
    source: Schema,
    target: Schema,
    dialect: Dialect,
    *,
    strict_column_order: bool = False,
    detect_renames: bool = False,
) -> tuple[Change, ...]:
    """Return the changes that turn ``source`` into ``target``.

    Names are compared the way ``dialect`` resolves them. Constraints and indexes are paired
    by definition; their names only count when both sides name them explicitly, so a
    constraint the database named on its own never shows up as a difference. The order of
    table columns is ignored unless ``strict_column_order`` is set.

    With ``detect_renames``, every :func:`possible rename <possible_renames>` becomes a
    :class:`RenameTable` or :class:`RenameColumn` at the start of the changes; the other
    changes then use the new names. Tables are paired first, so that the columns of a
    renamed table can be compared and renamed too.
    """
    differ = _Differ(dialect, strict_column_order=strict_column_order)
    changes = tuple(differ.schemas(source, target))
    if not detect_renames:
        return changes
    tables = _renames(changes, RenameTable)
    renamed = apply_renames(source, tables, dialect)
    columns = _renames(tuple(differ.schemas(renamed, target)), RenameColumn)
    renamed = apply_renames(renamed, columns, dialect)
    return (*tables, *columns, *differ.schemas(renamed, target))


def _renames(changes: Sequence[Change], kind: type[RenameChange]) -> list[Change]:
    return [
        candidate.rename
        for candidate in possible_renames(changes)
        if isinstance(candidate.rename, kind)
    ]


class _Differ:
    def __init__(self, dialect: Dialect, *, strict_column_order: bool) -> None:
        self._dialect = dialect
        self._strict_column_order = strict_column_order

    def schemas(self, source: Schema, target: Schema) -> Iterator[Change]:
        yield from self._enums(source.enums, target.enums)
        old_tables = {self._key(table.name): table for table in source.tables}
        new_tables = {self._key(table.name): table for table in target.tables}
        for key in sorted(old_tables.keys() | new_tables.keys()):
            if key not in new_tables:
                yield DropTable(old_tables[key])
            elif key not in old_tables:
                yield AddTable(new_tables[key])
            else:
                yield from self._table(old_tables[key], new_tables[key])

    def _enums(self, old: Sequence[EnumType], new: Sequence[EnumType]) -> Iterator[Change]:
        old_enums = {self._key(enum.name): enum for enum in old}
        new_enums = {self._key(enum.name): enum for enum in new}
        for key in sorted(old_enums.keys() | new_enums.keys()):
            if key not in new_enums:
                yield DropEnum(old_enums[key])
            elif key not in old_enums:
                yield AddEnum(new_enums[key])
            elif old_enums[key].values != new_enums[key].values:
                yield AlterEnum(old_enums[key], new_enums[key])

    def _table(self, old: Table, new: Table) -> Iterator[Change]:
        name = old.name
        yield from self._columns(name, old, new)

        old_keys = (old.primary_key,) if old.primary_key is not None else ()
        new_keys = (new.primary_key,) if new.primary_key is not None else ()
        dropped_keys, added_keys = self._match(old_keys, new_keys, self._key_signature)
        yield from (DropPrimaryKey(name, key) for key in dropped_keys)
        yield from (AddPrimaryKey(name, key) for key in added_keys)

        dropped_fks, added_fks = self._match(
            old.foreign_keys, new.foreign_keys, self._foreign_key_signature
        )
        yield from (DropForeignKey(name, fk) for fk in dropped_fks)
        yield from (AddForeignKey(name, fk) for fk in added_fks)

        dropped_uniques, added_uniques = self._match(
            old.unique_constraints, new.unique_constraints, self._unique_signature
        )
        yield from (DropUnique(name, unique) for unique in dropped_uniques)
        yield from (AddUnique(name, unique) for unique in added_uniques)

        dropped_checks, added_checks = self._match(
            old.check_constraints, new.check_constraints, _check_signature
        )
        yield from (DropCheck(name, check) for check in dropped_checks)
        yield from (AddCheck(name, check) for check in added_checks)

        dropped_indexes, added_indexes = self._match(
            old.indexes, new.indexes, self._index_signature
        )
        yield from (DropIndex(name, index) for index in dropped_indexes)
        yield from (AddIndex(name, index) for index in added_indexes)

    def _columns(self, table: str, old: Table, new: Table) -> Iterator[Change]:
        old_columns = {self._key(column.name): column for column in old.columns}
        new_columns = {self._key(column.name): column for column in new.columns}
        for key, column in old_columns.items():
            if key not in new_columns:
                yield DropColumn(table, column)
        for key, column in new_columns.items():
            if key not in old_columns:
                yield AddColumn(table, column)
        for key, column in old_columns.items():
            if key in new_columns:
                yield from _column(table, column, new_columns[key])

        if self._strict_column_order:
            # Added columns always land at the end of the table.
            kept = [key for key in old_columns if key in new_columns]
            result = kept + [key for key in new_columns if key not in old_columns]
            if result != list(new_columns):
                yield ReorderColumns(table, old.column_names, new.column_names)

    def _match(
        self,
        old: Sequence[_T],
        new: Sequence[_T],
        signature: Callable[[_T], Hashable],
    ) -> tuple[list[_T], list[_T]]:
        """Pair equal objects; return the unpaired ones as ``(dropped, added)``.

        Objects pair when their definitions match and their names do not contradict each
        other. Pairs with the same explicit name are formed first, so that a named object is
        not taken by an unnamed twin while its namesake is left over.
        """
        unpaired_new = list(new)
        pending = list(old)
        for same_name_only in (True, False):
            still_pending = []
            for item in pending:
                partner = next(
                    (
                        candidate
                        for candidate in unpaired_new
                        if signature(candidate) == signature(item)
                        and self._names_agree(item.name, candidate.name, same_name_only)
                    ),
                    None,
                )
                if partner is None:
                    still_pending.append(item)
                else:
                    unpaired_new.remove(partner)
            pending = still_pending
        return pending, unpaired_new

    def _names_agree(self, old: str | None, new: str | None, same_name_only: bool) -> bool:
        if old is None or new is None:
            return not same_name_only
        return self._key(old) == self._key(new)

    def _key(self, name: str) -> str:
        return name_key(name, self._dialect)

    def _keys(self, names: Sequence[str]) -> tuple[str, ...]:
        return tuple(self._key(name) for name in names)

    def _key_signature(self, key: PrimaryKey) -> Hashable:
        return self._keys(key.columns)

    def _foreign_key_signature(self, fk: ForeignKey) -> Hashable:
        return (
            self._keys(fk.columns),
            self._key(fk.ref_table),
            self._keys(fk.ref_columns),
            fk.on_delete,
            fk.on_update,
        )

    def _unique_signature(self, unique: UniqueConstraint) -> Hashable:
        return self._keys(unique.columns)

    def _index_signature(self, index: Index) -> Hashable:
        elements = tuple(
            (
                self._key(element.key) if isinstance(element.key, str) else element.key.sql,
                element.descending,
            )
            for element in index.elements
        )
        where = index.where.sql if index.where is not None else None
        return (elements, index.unique, where, index.method)


def _column(table: str, old: Column, new: Column) -> Iterator[Change]:
    name = old.name
    if old.type != new.type:
        yield AlterColumnType(table, name, old.type, new.type)
    if old.identity != new.identity:
        yield AlterIdentity(table, name, old.identity, new.identity)
    if new.default is not None and new.default != old.default:
        yield SetDefault(table, name, old.default, new.default)
    elif new.default is None and old.default is not None:
        yield DropDefault(table, name, old.default)
    if old.nullable and not new.nullable:
        yield SetNotNull(table, name)
    elif new.nullable and not old.nullable:
        yield DropNotNull(table, name)


def _check_signature(check: CheckConstraint) -> Hashable:
    return check.expression.sql
