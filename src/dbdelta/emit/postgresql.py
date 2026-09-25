"""SQL generation for PostgreSQL 14 and newer."""

from typing import ClassVar, assert_never

from dbdelta.dialects import Dialect, name_key
from dbdelta.dialects.postgresql import (
    backs_foreign_key,
    check_name,
    default_name,
    foreign_key_name,
    index_name,
    is_builtin,
    needs_explicit_cast,
    primary_key_name,
    unique_name,
)
from dbdelta.dialects.quoting import quote_identifier, quote_literal, quote_qualified
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
from dbdelta.emit.base import EmitOptions, Emitter, RiskNotes
from dbdelta.emit.script import Block, Script, Statement
from dbdelta.model import (
    Column,
    DataType,
    EnumType,
    Identity,
    Index,
    Schema,
)
from dbdelta.plan import MigrationPlan, Operation, RebuildTable, ReplaceEnum, describe_operation

_SERIAL_TYPES = {"smallint": "smallserial", "integer": "serial", "bigint": "bigserial"}

_IDENTITY_KINDS = {Identity.ALWAYS: "ALWAYS", Identity.BY_DEFAULT: "BY DEFAULT"}

_ENUM_BLOCK_COMMENT = (
    "New enum values are committed first: PostgreSQL cannot use an enum value in the\n"
    "transaction that added it."
)
_CONCURRENT_BLOCK_COMMENT = (
    "CONCURRENTLY cannot run inside a transaction. If a statement fails, drop the INVALID\n"
    "index it leaves behind before running it again."
)


class PostgresEmitter(Emitter):
    """Writes PostgreSQL migrations.

    DDL is transactional in PostgreSQL, so the migration runs in one transaction, except for
    new enum values, which must be committed before use, and, when requested, index builds
    with CONCURRENTLY, which cannot run in a transaction at all.
    """

    dialect: ClassVar[Dialect] = Dialect.POSTGRESQL

    def _emit(self, plan: MigrationPlan, options: EmitOptions, notes: RiskNotes) -> Script:
        enum_values: list[Statement] = []
        drops_first: list[Statement] = []
        main: list[Statement] = []
        builds_last: list[Statement] = []
        for operation in plan.operations:
            statements = self._statements(operation, plan, options, notes)
            if isinstance(operation, AlterEnum):
                enum_values += statements
            elif isinstance(operation, DropIndex) and self._concurrent(operation, plan, options):
                drops_first += statements
            elif isinstance(operation, AddIndex) and self._concurrent(operation, plan, options):
                builds_last += statements
            else:
                main += statements
        blocks = (
            Block(tuple(drops_first), transactional=False, comment=_CONCURRENT_BLOCK_COMMENT),
            Block(tuple(enum_values), transactional=True, comment=_ENUM_BLOCK_COMMENT),
            Block(tuple(main), transactional=True),
            Block(tuple(builds_last), transactional=False, comment=_CONCURRENT_BLOCK_COMMENT),
        )
        return Script(tuple(block for block in blocks if block.statements))

    def _statements(
        self, operation: Operation, plan: MigrationPlan, options: EmitOptions, notes: RiskNotes
    ) -> list[Statement]:
        comment = notes.comment(operation, describe_operation(operation))
        if isinstance(operation, ReorderColumns):
            note = "PostgreSQL cannot reorder columns; the column order stays as it is."
            return [Statement("", f"{comment}\n{note}")]
        sql = self._sql(operation, plan, options)
        return [Statement(sql[0], comment), *(Statement(text) for text in sql[1:])]

    def _sql(self, operation: Operation, plan: MigrationPlan, options: EmitOptions) -> list[str]:
        match operation:
            case AddEnum(enum):
                return [self._create_enum(enum)]
            case DropEnum(enum):
                return [f"DROP TYPE {quote_qualified(enum.name)}"]
            case AlterEnum(old, new):
                return self._add_enum_values(old, new)
            case ReplaceEnum(old, new, columns):
                return self._replace_enum(old, new, columns)
            case AddTable(table):
                return [self.create_table(table)] + [
                    self.create_index(table.name, index) for index in table.indexes
                ]
            case DropTable(table):
                return [f"DROP TABLE {quote_identifier(table.name)}"]
            case RenameTable(table, new_name):
                return [f"{_alter(table)} RENAME TO {quote_identifier(new_name)}"]
            case RenameColumn(table, column, new_name):
                return [
                    f"{_alter(table)} RENAME COLUMN {quote_identifier(column)} "
                    f"TO {quote_identifier(new_name)}"
                ]
            case AddColumn(table, column):
                return [f"{_alter(table)} ADD COLUMN {self.column_sql(column)}"]
            case DropColumn(table, column):
                return [f"{_alter(table)} DROP COLUMN {quote_identifier(column.name)}"]
            case AlterColumnType(table, column, old, new):
                return [self._alter_type(table, column, old, new)]
            case SetNotNull(table, column):
                return [f"{_alter_column(table, column)} SET NOT NULL"]
            case DropNotNull(table, column):
                return [f"{_alter_column(table, column)} DROP NOT NULL"]
            case SetDefault(table, column, _, default):
                return [f"{_alter_column(table, column)} SET DEFAULT {default}"]
            case DropDefault(table, column, _):
                return [f"{_alter_column(table, column)} DROP DEFAULT"]
            case AlterIdentity(table, column, old, new):
                return self._alter_identity(table, column, old, new, plan.target)
            case AddPrimaryKey(table, key):
                return [f"{_alter(table)} ADD {self.primary_key_sql(key)}"]
            case DropPrimaryKey(table, key):
                return [_drop_constraint(table, primary_key_name(table, key))]
            case AddUnique(table, unique):
                return [f"{_alter(table)} ADD {self.unique_sql(unique)}"]
            case DropUnique(table, unique):
                return [_drop_constraint(table, unique_name(table, unique))]
            case AddCheck(table, check):
                return [f"{_alter(table)} ADD {self.check_sql(check)}"]
            case DropCheck(table, check):
                return [_drop_constraint(table, check_name(table, check))]
            case AddForeignKey(table, fk):
                return [f"{_alter(table)} ADD {self.foreign_key_sql(fk)}"]
            case DropForeignKey(table, fk):
                return [_drop_constraint(table, foreign_key_name(table, fk))]
            case AddIndex(table, index):
                concurrently = self._concurrent(operation, plan, options)
                return [self.create_index(table, index, concurrently=concurrently)]
            case DropIndex(table, index):
                mode = "CONCURRENTLY " if self._concurrent(operation, plan, options) else ""
                return [f"DROP INDEX {mode}{quote_identifier(self.index_name(table, index))}"]
            case RebuildTable() | ReorderColumns():
                raise ValueError(f"PostgreSQL cannot {describe_operation(operation)}")
            case _:
                assert_never(operation)

    def type_sql(self, data_type: DataType) -> str:
        name = data_type.name
        if is_builtin(data_type) or " " in name or "(" in name:
            text = name
        else:
            text = quote_qualified(name)
        if data_type.params:
            text += "(" + ",".join(str(param) for param in data_type.params) + ")"
        return text + ("[]" if data_type.is_array else "")

    def column_sql(self, column: Column) -> str:
        if column.identity is Identity.SERIAL and column.type.name in _SERIAL_TYPES:
            parts = [quote_identifier(column.name), _SERIAL_TYPES[column.type.name]]
        else:
            parts = [quote_identifier(column.name), self.type_sql(column.type)]
        if not column.nullable:
            parts.append("NOT NULL")
        if column.default is not None:
            parts.append(f"DEFAULT {column.default}")
        if column.identity in _IDENTITY_KINDS:
            parts.append(f"GENERATED {_IDENTITY_KINDS[column.identity]} AS IDENTITY")
        return " ".join(parts)

    def index_name(self, table: str, index: Index) -> str:
        return index_name(table, index)

    def _create_enum(self, enum: EnumType) -> str:
        values = ", ".join(quote_literal(value) for value in enum.values)
        return f"CREATE TYPE {quote_qualified(enum.name)} AS ENUM ({values})"

    def _add_enum_values(self, old: EnumType, new: EnumType) -> list[str]:
        statements = []
        existing = set(old.values)
        for position, value in enumerate(new.values):
            if value in existing:
                continue
            if position > 0:
                place = f"AFTER {quote_literal(new.values[position - 1])}"
            else:
                following = next(later for later in new.values if later in existing)
                place = f"BEFORE {quote_literal(following)}"
            statements.append(
                f"ALTER TYPE {quote_qualified(old.name)} ADD VALUE {quote_literal(value)} {place}"
            )
            existing.add(value)
        return statements

    def _replace_enum(
        self, old: EnumType, new: EnumType, columns: tuple[tuple[str, Column], ...]
    ) -> list[str]:
        retired = f"{old.name}__dbdelta_old"
        statements = [
            f"ALTER TYPE {quote_qualified(old.name)} RENAME TO {quote_identifier(retired)}",
            self._create_enum(new),
        ]
        for table, column in columns:
            # A default still has the retired type and cannot be converted automatically.
            if column.default is not None:
                statements.append(f"{_alter_column(table, column.name)} DROP DEFAULT")
            target = self.type_sql(column.type)
            via = "text[]" if column.type.is_array else "text"
            statements.append(
                f"{_alter_column(table, column.name)} TYPE {target}"
                f" USING {quote_identifier(column.name)}::{via}::{target}"
            )
            if column.default is not None:
                statements.append(
                    f"{_alter_column(table, column.name)} SET DEFAULT {column.default}"
                )
        statements.append(f"DROP TYPE {quote_identifier(retired)}")
        return statements

    def _alter_type(self, table: str, column: str, old: DataType, new: DataType) -> str:
        target = self.type_sql(new)
        sql = f"{_alter_column(table, column)} TYPE {target}"
        if not needs_explicit_cast(old, new):
            return sql
        value = quote_identifier(column)
        if not is_builtin(old):
            # Enum values only convert to other types through their text form.
            value += "::text[]" if old.is_array else "::text"
        return f"{sql} USING {value}::{target}"

    def _alter_identity(
        self,
        table: str,
        column: str,
        old: Identity | None,
        new: Identity | None,
        target: Schema,
    ) -> list[str]:
        prefix = _alter_column(table, column)
        statements: list[str] = []
        if old in _IDENTITY_KINDS and new in _IDENTITY_KINDS:
            return [f"{prefix} SET GENERATED {_IDENTITY_KINDS[new]}"]
        if old in _IDENTITY_KINDS:
            statements.append(f"{prefix} DROP IDENTITY")
        elif old is Identity.SERIAL:
            # The sequence stays owned by the column and is dropped together with it.
            statements.append(f"{prefix} DROP DEFAULT")
        if new in _IDENTITY_KINDS:
            statements += [
                f"{prefix} ADD GENERATED {_IDENTITY_KINDS[new]} AS IDENTITY",
                _continue_sequence(
                    f"pg_get_serial_sequence({_regclass(table)}, {quote_literal(column)})",
                    table,
                    column,
                ),
            ]
        elif new is Identity.SERIAL:
            statements += self._make_serial(table, column, target)
        if not statements:
            raise ValueError(f"PostgreSQL has no {old} or {new} identity for {table}.{column}")
        return statements

    def _make_serial(self, table: str, column: str, target: Schema) -> list[str]:
        sequence = default_name(table, [column], "seq")
        data_type = _column_type(target, table, column)
        return [
            f"CREATE SEQUENCE {quote_identifier(sequence)} AS {self.type_sql(data_type)}"
            f" OWNED BY {quote_identifier(table)}.{quote_identifier(column)}",
            _continue_sequence(_regclass(sequence), table, column),
            f"{_alter_column(table, column)} SET DEFAULT nextval({_regclass(sequence)}::regclass)",
        ]

    def _concurrent(self, operation: Operation, plan: MigrationPlan, options: EmitOptions) -> bool:
        """Tell whether an index change can run concurrently, outside the transaction.

        A unique index that a foreign key relies on stays in the transaction, next to the
        foreign key changes that depend on it.
        """
        if not options.concurrent_indexes:
            return False
        if isinstance(operation, AddIndex):
            schema, table, index = plan.target, operation.table, operation.index
        elif isinstance(operation, DropIndex):
            schema, table, index = plan.source, operation.table, operation.index
        else:
            return False
        return not backs_foreign_key(schema, table, index)


def _alter(table: str) -> str:
    return f"ALTER TABLE {quote_identifier(table)}"


def _alter_column(table: str, column: str) -> str:
    return f"{_alter(table)} ALTER COLUMN {quote_identifier(column)}"


def _drop_constraint(table: str, name: str) -> str:
    return f"{_alter(table)} DROP CONSTRAINT {quote_identifier(name)}"


def _regclass(name: str) -> str:
    """A quoted identifier as the text literal that functions taking regclass expect."""
    return quote_literal(quote_identifier(name))


def _continue_sequence(sequence: str, table: str, column: str) -> str:
    """Move a sequence past the values already in the column, so new rows do not collide."""
    return (
        f"SELECT setval({sequence}, COALESCE(MAX({quote_identifier(column)}), 0) + 1, false)"
        f" FROM {quote_identifier(table)}"
    )


def _column_type(schema: Schema, table: str, column: str) -> DataType:
    for candidate in schema.tables:
        if name_key(candidate.name, Dialect.POSTGRESQL) == name_key(table, Dialect.POSTGRESQL):
            found = candidate.column(column)
            if found is not None:
                return found.type
    return DataType("integer")
