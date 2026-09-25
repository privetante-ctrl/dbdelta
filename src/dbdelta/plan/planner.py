"""Order changes so that every statement finds the objects it needs.

Operations run in phases: renames come first, because the other changes use the new names;
then everything that depends on something about to go is removed, then objects are
dropped, then created, and foreign keys come last because they depend on tables, columns
and keys all being in place:

1. rename tables
2. rename columns
3. drop foreign keys
4. drop indexes, CHECK, UNIQUE and primary key constraints
5. drop columns
6. drop tables, dependents first
7. create, extend and recreate enum types
8. create tables, referenced tables first
9. add columns
10. alter columns, or rebuild tables where ALTER TABLE cannot change them
11. add primary key, UNIQUE and CHECK constraints
12. create indexes
13. add foreign keys
14. drop enum types, once no column uses them

In dialects that check foreign keys in DDL, foreign keys that form a cycle between new
tables are split off into step 13, and foreign keys that depend on a key being replaced
are dropped in step 3 and added back in step 13. A column whose type and default both
change loses its old default before the type changes.

In dialects whose ALTER TABLE cannot change column definitions or constraints (SQLite),
all changes to such a table become one :class:`RebuildTable`. An enum type whose values
are not simply extended becomes a :class:`ReplaceEnum`.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace

from dbdelta.dialects import Dialect, name_key
from dbdelta.dialects.sqlite import can_add_column
from dbdelta.diff import (
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
    apply_renames,
)
from dbdelta.model import Column, EnumType, ForeignKey, Index, Schema, Table
from dbdelta.plan.graph import order_by_dependencies
from dbdelta.plan.operations import Operation, RebuildTable, ReplaceEnum, describe_operation

_PHASES: dict[type, int] = {
    RenameTable: 1,
    RenameColumn: 2,
    DropForeignKey: 3,
    DropIndex: 4,
    DropCheck: 4,
    DropUnique: 4,
    DropPrimaryKey: 4,
    DropColumn: 5,
    DropTable: 6,
    AddEnum: 7,
    AlterEnum: 7,
    ReplaceEnum: 7,
    AddTable: 8,
    AddColumn: 9,
    DropDefault: 10,
    DropNotNull: 10,
    AlterColumnType: 10,
    AlterIdentity: 10,
    SetDefault: 10,
    SetNotNull: 10,
    ReorderColumns: 10,
    RebuildTable: 10,
    AddPrimaryKey: 11,
    AddUnique: 11,
    AddCheck: 11,
    AddIndex: 12,
    AddForeignKey: 13,
    DropEnum: 14,
}

_KeyRef = tuple[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """The operations of a migration, in an order in which they can be executed."""

    operations: tuple[Operation, ...]
    source: Schema
    target: Schema
    dialect: Dialect


def plan_migration(
    changes: Iterable[Change], source: Schema, target: Schema, dialect: Dialect
) -> MigrationPlan:
    """Order ``changes``, which turn ``source`` into ``target``, for execution.

    The plan's ``source`` is the schema after the renames among ``changes``, which is the
    schema the other operations address.
    """
    changes = list(changes)
    source = apply_renames(source, changes, dialect)
    operations = _Planner(dialect).plan(changes, source, target)
    return MigrationPlan(tuple(operations), source, target, dialect)


class _Planner:
    def __init__(self, dialect: Dialect) -> None:
        self._dialect = dialect
        self._checks_foreign_keys = dialect.traits.checks_foreign_keys_in_ddl
        self._column_positions: dict[tuple[str, str], int] = {}

    def plan(self, changes: list[Change], source: Schema, target: Schema) -> Iterator[Operation]:
        # ADD COLUMN appends, so columns must be added in their target order.
        self._column_positions = {
            (self._key(table.name), self._key(column.name)): position
            for table in target.tables
            for position, column in enumerate(table.columns)
        }
        changes += self._release_replaced_defaults(changes)
        if self._checks_foreign_keys:
            changes += self._rebuild_foreign_keys_on_replaced_keys(changes, source)
        dropped = [change for change in changes if isinstance(change, DropTable)]
        added = [change for change in changes if isinstance(change, AddTable)]
        others: list[Change] = [
            change for change in changes if not isinstance(change, AddTable | DropTable)
        ]

        drop_order, cycle_foreign_keys = self._drop_order(dropped)
        create_order, deferred_foreign_keys = self._create_order(added, changes)
        others += cycle_foreign_keys + deferred_foreign_keys
        operations = self._replace_enums(others, source, target)
        if not self._dialect.traits.alters_table_definitions:
            operations = self._rebuild_tables(operations, source, target)

        phases: dict[int, list[Operation]] = {phase: [] for phase in _PHASES.values()}
        for operation in sorted(operations, key=self._position):
            phases[_PHASES[type(operation)]].append(operation)
        phases[_PHASES[DropTable]] = drop_order
        phases[_PHASES[AddTable]] = create_order
        for phase in sorted(phases):
            yield from phases[phase]

    def _drop_order(self, dropped: Sequence[DropTable]) -> tuple[list[Operation], list[Change]]:
        """Order dropped tables so that referencing tables go before referenced ones."""
        tables = {self._key(change.table.name): change for change in dropped}
        order = order_by_dependencies(
            {key: self._references(change.table) for key, change in tables.items()}
        )
        released: list[Change] = []
        if self._checks_foreign_keys:
            for dependent, dependency in sorted(order.broken):
                table = tables[dependent].table
                released += [
                    DropForeignKey(table.name, fk)
                    for fk in table.foreign_keys
                    if self._key(fk.ref_table) == dependency
                ]
        return [tables[key] for key in reversed(order.order)], released

    def _create_order(
        self, added: Sequence[AddTable], changes: Sequence[Change]
    ) -> tuple[list[Operation], list[Change]]:
        """Order new tables so that referenced tables are created first.

        Where the dialect checks foreign keys in DDL, a foreign key is created separately
        after all tables if it closes a cycle or references a key created later.
        """
        tables = {self._key(change.table.name): change.table for change in added}
        order = order_by_dependencies(
            {key: self._references(table) for key, table in tables.items()}
        )
        if not self._checks_foreign_keys:
            return [AddTable(tables[key]) for key in order.order], []

        later_keys = self._created_keys(changes)
        creates: list[Operation] = []
        deferred: list[Change] = []
        for key in order.order:
            table = tables[key]
            inline: list[ForeignKey] = []
            for fk in table.foreign_keys:
                target = self._key(fk.ref_table)
                if (key, target) in order.broken or self._key_ref(fk) in later_keys:
                    deferred.append(AddForeignKey(table.name, fk))
                else:
                    inline.append(fk)
            creates.append(AddTable(replace(table, foreign_keys=tuple(inline))))
        return creates, deferred

    def _rebuild_foreign_keys_on_replaced_keys(
        self, changes: Sequence[Change], source: Schema
    ) -> list[Change]:
        """Drop and re-add surviving foreign keys whose referenced key is being dropped."""
        dropped_keys = {
            self._table_key_ref(change.table, columns)
            for change in changes
            if isinstance(change, DropPrimaryKey | DropUnique | DropIndex)
            for columns in _key_columns(change)
        }
        dropped_tables = {
            self._key(change.table.name) for change in changes if isinstance(change, DropTable)
        }
        dropped_fks = {
            (self._key(change.table), change.foreign_key)
            for change in changes
            if isinstance(change, DropForeignKey)
        }
        rebuilt: list[Change] = []
        for table in source.tables:
            if self._key(table.name) in dropped_tables:
                continue
            for fk in table.foreign_keys:
                if (
                    self._key_ref(fk) in dropped_keys
                    and (self._key(table.name), fk) not in dropped_fks
                ):
                    rebuilt += [DropForeignKey(table.name, fk), AddForeignKey(table.name, fk)]
        return rebuilt

    def _replace_enums(
        self, changes: Sequence[Change], source: Schema, target: Schema
    ) -> list[Operation]:
        """Turn enum changes that do more than add values into :class:`ReplaceEnum`."""
        operations: list[Operation] = []
        for change in changes:
            if isinstance(change, AlterEnum) and not _extends(change.old, change.new):
                columns = self._enum_columns(change.old, source, target)
                operations.append(ReplaceEnum(change.old, change.new, columns))
            else:
                operations.append(change)
        return operations

    def _enum_columns(
        self, enum: EnumType, source: Schema, target: Schema
    ) -> tuple[tuple[str, Column], ...]:
        """Existing columns that use ``enum`` before and after the migration."""
        uses: list[tuple[str, Column]] = []
        for old_table in source.tables:
            new_table = self._find_table(target, old_table.name)
            if new_table is None:
                continue
            for column in new_table.columns:
                old_column = self._find_column(old_table, column.name)
                if (
                    old_column is not None
                    and self._key(old_column.type.name) == self._key(enum.name)
                    and self._key(column.type.name) == self._key(enum.name)
                ):
                    uses.append((old_table.name, column))
        return tuple(uses)

    def _rebuild_tables(
        self, operations: Sequence[Operation], source: Schema, target: Schema
    ) -> list[Operation]:
        """Replace the changes to a table that ALTER TABLE cannot make by a rebuild."""
        by_table: dict[str, list[Change]] = {}
        for operation in operations:
            if isinstance(operation, _TABLE_CHANGES):
                by_table.setdefault(self._key(operation.table), []).append(operation)

        rebuilt: dict[str, RebuildTable] = {}
        for key, changes in by_table.items():
            if all(_alters_in_place(change) for change in changes):
                continue
            old, new = self._find_table(source, key), self._find_table(target, key)
            if old is not None and new is not None:
                rebuilt[key] = RebuildTable(old, new, tuple(changes))

        result: list[Operation] = [
            operation
            for operation in operations
            if not (isinstance(operation, _TABLE_CHANGES) and self._key(operation.table) in rebuilt)
        ]
        return result + list(rebuilt.values())

    def _find_table(self, schema: Schema, name: str) -> Table | None:
        key = self._key(name)
        return next((table for table in schema.tables if self._key(table.name) == key), None)

    def _find_column(self, table: Table, name: str) -> Column | None:
        key = self._key(name)
        return next((column for column in table.columns if self._key(column.name) == key), None)

    def _release_replaced_defaults(self, changes: Sequence[Change]) -> list[Change]:
        """Drop the old default of a column whose type and default both change.

        The old default would otherwise have to be converted to the new type, which fails
        when no automatic cast exists, and it is about to be replaced anyway.
        """
        retyped = {
            (self._key(change.table), self._key(change.column))
            for change in changes
            if isinstance(change, AlterColumnType)
        }
        return [
            DropDefault(change.table, change.column, change.old)
            for change in changes
            if isinstance(change, SetDefault)
            and change.old is not None
            and (self._key(change.table), self._key(change.column)) in retyped
        ]

    def _created_keys(self, changes: Sequence[Change]) -> set[_KeyRef]:
        return {
            self._table_key_ref(change.table, columns)
            for change in changes
            if isinstance(change, AddPrimaryKey | AddUnique | AddIndex)
            for columns in _key_columns(change)
        }

    def _references(self, table: Table) -> set[str]:
        return {self._key(fk.ref_table) for fk in table.foreign_keys}

    def _key_ref(self, fk: ForeignKey) -> _KeyRef:
        return self._table_key_ref(fk.ref_table, fk.ref_columns)

    def _table_key_ref(self, table: str, columns: Iterable[str]) -> _KeyRef:
        return self._key(table), frozenset(self._key(column) for column in columns)

    def _key(self, name: str) -> str:
        return name_key(name, self._dialect)

    def _position(self, operation: Operation) -> tuple[str, int, int, str]:
        subject = self._key(_subject(operation))
        column = 0
        if isinstance(operation, AddColumn):
            column = self._column_positions[(subject, self._key(operation.column.name))]
        return (subject, _column_step(operation), column, describe_operation(operation))


_TABLE_CHANGES = (
    AddColumn,
    DropColumn,
    AlterColumnType,
    SetNotNull,
    DropNotNull,
    SetDefault,
    DropDefault,
    AlterIdentity,
    ReorderColumns,
    AddPrimaryKey,
    DropPrimaryKey,
    AddForeignKey,
    DropForeignKey,
    AddUnique,
    DropUnique,
    AddCheck,
    DropCheck,
    AddIndex,
    DropIndex,
)


def _alters_in_place(change: Change) -> bool:
    """Tell whether SQLite's limited ALTER TABLE can make ``change``."""
    if isinstance(change, AddColumn):
        return can_add_column(change.column)
    return isinstance(change, DropColumn | AddIndex | DropIndex)


def _extends(old: EnumType, new: EnumType) -> bool:
    """Tell whether ``new`` only adds values to ``old``, keeping their order."""
    remaining = iter(new.values)
    return all(value in remaining for value in old.values)


def _column_step(operation: Operation) -> int:
    """Order of the changes to one column.

    A default goes before the type changes under it, and NOT NULL is enforced once the type
    is final. PostgreSQL requires NOT NULL before a column becomes an identity column and
    refuses to drop NOT NULL while it still is one.
    """
    match operation:
        case AlterIdentity(new=None):
            return 0
        case DropDefault():
            return 1
        case DropNotNull():
            return 2
        case AlterColumnType():
            return 3
        case SetNotNull():
            return 4
        case AlterIdentity():
            return 5
        case SetDefault():
            return 6
        case _:
            return 7


def _subject(operation: Operation) -> str:
    """Name of the table or enum type an operation applies to."""
    match operation:
        case AddEnum(enum) | DropEnum(enum):
            return enum.name
        case AlterEnum(old, _) | ReplaceEnum(old, _, _):
            return old.name
        case AddTable(table) | DropTable(table) | RebuildTable(table, _, _):
            return table.name
        case _:
            return operation.table


def _key_columns(change: Change) -> list[tuple[str, ...]]:
    """Columns of the key that a change adds or drops, if it is one a foreign key can use."""
    match change:
        case AddPrimaryKey(_, key) | DropPrimaryKey(_, key):
            return [key.columns]
        case AddUnique(_, constraint) | DropUnique(_, constraint):
            return [constraint.columns]
        case AddIndex(_, index) | DropIndex(_, index) if _is_plain_unique(index):
            return [tuple(str(element.key) for element in index.elements)]
        case _:
            return []


def _is_plain_unique(index: Index) -> bool:
    return (
        index.unique
        and index.where is None
        and all(isinstance(element.key, str) for element in index.elements)
    )
