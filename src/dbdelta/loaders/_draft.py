"""Mutable drafts that loaders fill in before freezing them into the model.

Both loaders collect objects into these drafts, and :meth:`SchemaDraft.build` applies the
rules that must hold whatever the source: references resolve to declared names, foreign
keys without a column list point at the primary key, and primary key columns are NOT NULL.
"""

from dataclasses import dataclass, field, replace

from dbdelta.dialects import Dialect, name_key
from dbdelta.loaders.base import LoadError, LoadResult
from dbdelta.model import (
    CheckConstraint,
    Column,
    EnumType,
    Expression,
    ForeignKey,
    Index,
    IndexElement,
    PrimaryKey,
    ReferentialAction,
    Schema,
    Table,
    UniqueConstraint,
)


@dataclass(slots=True)
class ForeignKeyDraft:
    """A foreign key whose referenced columns may still be implicit."""

    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]
    on_delete: ReferentialAction = ReferentialAction.NO_ACTION
    on_update: ReferentialAction = ReferentialAction.NO_ACTION
    name: str | None = None


@dataclass(slots=True)
class TableDraft:
    """A table under construction. ``columns`` preserves declaration order."""

    name: str
    dialect: Dialect
    columns: dict[str, Column] = field(default_factory=dict)
    primary_key: PrimaryKey | None = None
    foreign_keys: list[ForeignKeyDraft] = field(default_factory=list)
    unique_constraints: list[UniqueConstraint] = field(default_factory=list)
    check_constraints: list[CheckConstraint] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)

    def find_column(self, name: str) -> Column | None:
        """Look a column up the way the dialect resolves column names."""
        key = name_key(name, self.dialect)
        return next(
            (col for col in self.columns.values() if name_key(col.name, self.dialect) == key),
            None,
        )

    def resolve(self, name: str) -> str:
        """Return the declared spelling of a column name, or ``name`` if it is unknown."""
        column = self.find_column(name)
        return column.name if column is not None else name

    def add_column(self, column: Column) -> None:
        if self.find_column(column.name) is not None:
            raise LoadError(f"table {self.name!r} declares column {column.name!r} twice")
        self.columns[column.name] = column

    def replace_column(self, column: Column) -> None:
        self.columns[column.name] = column

    def set_primary_key(self, primary_key: PrimaryKey) -> None:
        if self.primary_key is not None:
            raise LoadError(f"table {self.name!r} declares more than one primary key")
        self.primary_key = primary_key


class SchemaDraft:
    """Tables and enum types collected from a source, plus warnings for the user."""

    def __init__(self, dialect: Dialect) -> None:
        self.dialect = dialect
        self.warnings: list[str] = []
        self._tables: dict[str, TableDraft] = {}
        self._enums: dict[str, EnumType] = {}

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def table(self, name: str) -> TableDraft | None:
        return self._tables.get(name_key(name, self.dialect))

    def tables(self) -> list[TableDraft]:
        return list(self._tables.values())

    def add_table(self, table: TableDraft) -> None:
        if self.table(table.name) is not None:
            raise LoadError(f"table {table.name!r} is defined more than once")
        self._tables[name_key(table.name, self.dialect)] = table

    def drop_table(self, name: str) -> None:
        self._tables.pop(name_key(name, self.dialect), None)

    def enum(self, name: str) -> EnumType | None:
        return self._enums.get(name_key(name, self.dialect))

    def add_enum(self, enum: EnumType) -> None:
        if self.enum(enum.name) is not None:
            raise LoadError(f"type {enum.name!r} is defined more than once")
        self._enums[name_key(enum.name, self.dialect)] = enum

    def drop_enum(self, name: str) -> None:
        self._enums.pop(name_key(name, self.dialect), None)

    def build(self) -> LoadResult:
        """Resolve references and freeze the draft into a :class:`Schema`."""
        try:
            tables = tuple(self._build_table(table) for table in self._tables.values())
            schema = Schema(tables, tuple(self._enums.values()))
        except ValueError as error:
            raise LoadError(str(error)) from error
        return LoadResult(schema, tuple(self.warnings))

    def _build_table(self, draft: TableDraft) -> Table:
        primary_key = draft.primary_key
        if primary_key is not None:
            primary_key = replace(primary_key, columns=_resolve_all(draft, primary_key.columns))
        key_columns = set(primary_key.columns) if primary_key is not None else set()
        # PostgreSQL enforces NOT NULL on key columns; SQLite only fails to because of a
        # documented legacy bug, so treating them as NOT NULL everywhere is the faithful form.
        columns = tuple(
            replace(column, nullable=False) if column.name in key_columns else column
            for column in draft.columns.values()
        )
        return Table(
            name=draft.name,
            columns=columns,
            primary_key=primary_key,
            foreign_keys=tuple(self._build_foreign_key(draft, fk) for fk in draft.foreign_keys),
            unique_constraints=tuple(
                replace(unique, columns=_resolve_all(draft, unique.columns))
                for unique in draft.unique_constraints
            ),
            check_constraints=tuple(
                replace(check, expression=_resolve_expression(draft, check.expression))
                for check in draft.check_constraints
            ),
            indexes=tuple(_resolve_index(draft, index) for index in draft.indexes),
        )

    def _build_foreign_key(self, draft: TableDraft, fk: ForeignKeyDraft) -> ForeignKey:
        target = self.table(fk.ref_table)
        ref_table = target.name if target is not None else fk.ref_table
        ref_columns = fk.ref_columns
        if not ref_columns and target is not None and target.primary_key is not None:
            ref_columns = target.primary_key.columns
        if not ref_columns:
            raise LoadError(
                f"foreign key {fk.columns} of table {draft.name!r} references {ref_table!r} "
                "without a column list, and that table has no known primary key"
            )
        if target is not None:
            ref_columns = _resolve_all(target, ref_columns)
        return ForeignKey(
            columns=_resolve_all(draft, fk.columns),
            ref_table=ref_table,
            ref_columns=ref_columns,
            on_delete=fk.on_delete,
            on_update=fk.on_update,
            name=fk.name,
        )


def _resolve_all(draft: TableDraft, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(draft.resolve(name) for name in names)


def _resolve_expression(draft: TableDraft, expression: Expression) -> Expression:
    return replace(expression, columns=frozenset(draft.resolve(c) for c in expression.columns))


def _resolve_index(draft: TableDraft, index: Index) -> Index:
    elements = tuple(
        IndexElement(
            draft.resolve(element.key)
            if isinstance(element.key, str)
            else _resolve_expression(draft, element.key),
            element.descending,
        )
        for element in index.elements
    )
    where = _resolve_expression(draft, index.where) if index.where is not None else None
    return replace(index, elements=elements, where=where)
