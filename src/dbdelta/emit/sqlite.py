"""SQL generation for SQLite."""

from typing import ClassVar

from dbdelta.dialects import Dialect, name_key
from dbdelta.dialects.sqlite import is_constant
from dbdelta.diff import AddColumn, AddIndex, AddTable, DropColumn, DropIndex, DropTable, describe
from dbdelta.emit.base import EmitOptions, Emitter, index_key_names
from dbdelta.emit.quoting import quote_identifier
from dbdelta.emit.script import Block, Script, Statement
from dbdelta.model import Column, DataType, Identity, Index, PrimaryKey, Table
from dbdelta.plan import MigrationPlan, Operation, RebuildTable, describe_operation

_REBUILD_PREFIX = "_dbdelta_new_"

_FOREIGN_KEYS_OFF_COMMENT = (
    "Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's\n"
    "documented procedure for schema changes requires. PRAGMA foreign_keys has no\n"
    "effect inside a transaction, so it is set outside of it."
)
_FOREIGN_KEY_CHECK_COMMENT = "Lists rows that violate foreign keys; it must return no rows."


class SQLiteEmitter(Emitter):
    """Writes SQLite migrations.

    SQLite's ALTER TABLE can only add and drop columns; the planner turns every other change
    into a :class:`RebuildTable`, which follows the procedure from SQLite's documentation:
    create the new table, copy the rows, drop the old table, rename, recreate the indexes.
    """

    dialect: ClassVar[Dialect] = Dialect.SQLITE

    def _emit(self, plan: MigrationPlan, options: EmitOptions) -> Script:  # noqa: ARG002
        # None of the emit options applies to SQLite.
        statements = [
            statement for operation in plan.operations for statement in self._statements(operation)
        ]
        if not statements:
            return Script()
        replaces_tables = any(
            isinstance(operation, RebuildTable | DropTable) for operation in plan.operations
        )
        if not replaces_tables:
            return Script((Block(tuple(statements), transactional=True),))
        check = Statement("PRAGMA foreign_key_check", _FOREIGN_KEY_CHECK_COMMENT)
        return Script(
            (
                Block(
                    (Statement("PRAGMA foreign_keys = OFF"),),
                    transactional=False,
                    comment=_FOREIGN_KEYS_OFF_COMMENT,
                ),
                Block((*statements, check), transactional=True),
                Block((Statement("PRAGMA foreign_keys = ON"),), transactional=False),
            )
        )

    def _statements(self, operation: Operation) -> list[Statement]:
        match operation:
            case AddTable(table):
                sql = [self.create_table(table)]
                sql += [self.create_index(table.name, index) for index in table.indexes]
            case DropTable(table):
                sql = [f"DROP TABLE {quote_identifier(table.name)}"]
            case AddColumn(table, column):
                sql = [
                    f"ALTER TABLE {quote_identifier(table)} ADD COLUMN {self.column_sql(column)}"
                ]
            case DropColumn(table, column):
                sql = [
                    f"ALTER TABLE {quote_identifier(table)} DROP COLUMN "
                    f"{quote_identifier(column.name)}"
                ]
            case AddIndex(table, index):
                sql = [self.create_index(table, index)]
            case DropIndex(table, index):
                sql = [f"DROP INDEX {quote_identifier(self.index_name(table, index))}"]
            case RebuildTable():
                return self._rebuild(operation)
            case _:
                raise ValueError(
                    f"SQLite cannot {describe_operation(operation)} in place; "
                    "the table has to be rebuilt"
                )
        return [Statement(sql[0], describe_operation(operation)), *map(Statement, sql[1:])]

    def _rebuild(self, rebuild: RebuildTable) -> list[Statement]:
        old, new = rebuild.old, rebuild.new
        temporary = quote_identifier(_REBUILD_PREFIX + new.name)
        copied = [
            (column.name, source.name)
            for column in new.columns
            if (source := _find_column(old, column.name)) is not None
        ]
        sql = [self.create_table(new, _REBUILD_PREFIX + new.name)]
        if copied:
            targets = ", ".join(quote_identifier(target) for target, _ in copied)
            sources = ", ".join(quote_identifier(source) for _, source in copied)
            sql.append(
                f"INSERT INTO {temporary} ({targets}) "
                f"SELECT {sources} FROM {quote_identifier(old.name)}"
            )
        sql += [
            f"DROP TABLE {quote_identifier(old.name)}",
            f"ALTER TABLE {temporary} RENAME TO {quote_identifier(new.name)}",
        ]
        sql += [self.create_index(new.name, index) for index in new.indexes]
        reasons = "\n".join(f"  {describe(change)}" for change in rebuild.changes)
        comment = (
            f"{describe_operation(rebuild)}: SQLite cannot make these changes in place\n{reasons}"
        )
        return [Statement(sql[0], comment), *map(Statement, sql[1:])]

    def create_table(self, table: Table, name: str | None = None) -> str:
        key = _autoincrement_key(table)
        items = []
        for column in table.columns:
            definition = self.column_sql(column)
            if key is not None and column.name == key.columns[0]:
                constraint = f"CONSTRAINT {quote_identifier(key.name)} " if key.name else ""
                definition += f" {constraint}PRIMARY KEY AUTOINCREMENT"
            items.append(definition)
        items += self.table_constraints(table, primary_key=key is None)
        body = ",\n    ".join(items)
        return f"CREATE TABLE {quote_identifier(name or table.name)} (\n    {body}\n)"

    def type_sql(self, data_type: DataType) -> str:
        return str(data_type)

    def column_sql(self, column: Column) -> str:
        parts = [quote_identifier(column.name)]
        if column.type.name:
            parts.append(self.type_sql(column.type))
        if not column.nullable:
            parts.append("NOT NULL")
        if column.default is not None:
            # SQLite requires parentheses around any default that is not a literal.
            default = column.default if is_constant(column.default) else f"({column.default})"
            parts.append(f"DEFAULT {default}")
        return " ".join(parts)

    def index_name(self, table: str, index: Index) -> str:
        return index.name or "_".join(["ix", table, *index_key_names(index)])


def _autoincrement_key(table: Table) -> PrimaryKey | None:
    """The primary key if it is an AUTOINCREMENT column, which SQLite only accepts inline."""
    key = table.primary_key
    if key is None or len(key.columns) != 1:
        return None
    column = table.column(key.columns[0])
    return key if column is not None and column.identity is Identity.AUTOINCREMENT else None


def _find_column(table: Table, name: str) -> Column | None:
    key = name_key(name, Dialect.SQLITE)
    return next(
        (column for column in table.columns if name_key(column.name, Dialect.SQLITE) == key),
        None,
    )
