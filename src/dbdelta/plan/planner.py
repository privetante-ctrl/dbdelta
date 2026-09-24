"""Order changes so that every statement finds the objects it needs.

Operations run in phases: everything that depends on something about to go is removed
first, then objects are dropped, then created, and foreign keys come last because they
depend on tables, columns and keys all being in place:

1. drop foreign keys
2. drop indexes, CHECK, UNIQUE and primary key constraints
3. drop columns
4. drop tables, dependents first
5. create and alter enum types
6. create tables, referenced tables first
7. add columns
8. alter columns
9. add primary key, UNIQUE and CHECK constraints
10. create indexes
11. add foreign keys
12. drop enum types, once no column uses them

In dialects that check foreign keys in DDL, foreign keys that form a cycle between new
tables are split off into step 11, and foreign keys that depend on a key being replaced
are dropped in step 1 and added back in step 11. A column whose type and default both
change loses its old default before the type changes.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace

from dbdelta.dialects import Dialect, name_key
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
    ReorderColumns,
    SetDefault,
    SetNotNull,
    describe,
)
from dbdelta.model import ForeignKey, Index, Schema, Table
from dbdelta.plan.graph import order_by_dependencies

_PHASES: dict[type, int] = {
    DropForeignKey: 1,
    DropIndex: 2,
    DropCheck: 2,
    DropUnique: 2,
    DropPrimaryKey: 2,
    DropColumn: 3,
    DropTable: 4,
    AddEnum: 5,
    AlterEnum: 5,
    AddTable: 6,
    AddColumn: 7,
    DropDefault: 8,
    DropNotNull: 8,
    AlterColumnType: 8,
    AlterIdentity: 8,
    SetDefault: 8,
    SetNotNull: 8,
    ReorderColumns: 8,
    AddPrimaryKey: 9,
    AddUnique: 9,
    AddCheck: 9,
    AddIndex: 10,
    AddForeignKey: 11,
    DropEnum: 12,
}

# Within one column: a default must go before the type changes under it, and NOT NULL is
# enforced last, once the type and default are final.
_COLUMN_STEPS: dict[type, int] = {
    DropDefault: 1,
    DropNotNull: 2,
    AlterColumnType: 3,
    AlterIdentity: 4,
    SetDefault: 5,
    SetNotNull: 6,
    ReorderColumns: 7,
}

_KeyRef = tuple[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """The operations of a migration, in an order in which they can be executed."""

    operations: tuple[Change, ...]


def plan_migration(changes: Iterable[Change], source: Schema, dialect: Dialect) -> MigrationPlan:
    """Order ``changes``, which turn ``source`` into a target schema, for execution."""
    return MigrationPlan(tuple(_Planner(dialect).plan(list(changes), source)))


class _Planner:
    def __init__(self, dialect: Dialect) -> None:
        self._dialect = dialect
        self._checks_foreign_keys = dialect.traits.checks_foreign_keys_in_ddl

    def plan(self, changes: list[Change], source: Schema) -> Iterator[Change]:
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

        phases: dict[int, list[Change]] = {phase: [] for phase in _PHASES.values()}
        for change in sorted(others, key=self._position):
            phases[_PHASES[type(change)]].append(change)
        phases[_PHASES[DropTable]] = drop_order
        phases[_PHASES[AddTable]] = create_order
        for phase in sorted(phases):
            yield from phases[phase]

    def _drop_order(self, dropped: Sequence[DropTable]) -> tuple[list[Change], list[Change]]:
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
    ) -> tuple[list[Change], list[Change]]:
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
        creates: list[Change] = []
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

    def _position(self, change: Change) -> tuple[str, int, str]:
        return (self._key(_subject(change)), _COLUMN_STEPS.get(type(change), 0), describe(change))


def _subject(change: Change) -> str:
    """Name of the table or enum type a change applies to."""
    match change:
        case AddEnum(enum) | DropEnum(enum):
            return enum.name
        case AlterEnum(old, _):
            return old.name
        case AddTable(table) | DropTable(table):
            return table.name
        case _:
            return change.table


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
