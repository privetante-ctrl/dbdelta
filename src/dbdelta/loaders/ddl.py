"""Load a schema from DDL statements, such as a hand-written schema file or a dump.

Statements are applied in order, like a database executing the script: ``ALTER TABLE``
adds to earlier tables and ``DROP`` removes them. Statements that cannot change the
MVP objects (``SET``, ``GRANT``, ``INSERT``, ...) are ignored; statements about objects
dbdelta does not model (views, functions, ...) are skipped with a warning.

A statement that fails to parse is an error rather than a warning: silently missing a
``CREATE TABLE`` would make the migration drop that table.
"""

import re
from dataclasses import replace
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from dbdelta.dialects import Dialect, ascii_lower, name_key
from dbdelta.loaders._draft import ForeignKeyDraft, SchemaDraft, TableDraft
from dbdelta.loaders._sqlglot import WITHOUT_ROWID, sqlglot_dialect
from dbdelta.loaders.base import LoadError, LoadResult
from dbdelta.loaders.normalize import normalize_default, normalize_expression
from dbdelta.loaders.types import (
    canonical_type,
    fold_identifier,
    serial_type,
)
from dbdelta.model import (
    CheckConstraint,
    Column,
    DataType,
    EnumType,
    Identity,
    Index,
    IndexElement,
    PrimaryKey,
    ReferentialAction,
    UniqueConstraint,
)

_IGNORED_STATEMENTS = (
    exp.Set,
    exp.Select,
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Pragma,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Comment,
    exp.Grant,
    exp.Revoke,
    exp.Use,
    exp.Analyze,
    # A trailing comment after the last statement, such as pg_dump's "dump complete".
    exp.Semicolon,
)

_REFERENTIAL_ACTION = re.compile(
    r"ON (?P<event>DELETE|UPDATE) (?P<action>NO ACTION|RESTRICT|CASCADE|SET NULL|SET DEFAULT)"
)

# pg_dump emits "ALTER <object> ... OWNER TO <role>" for every object; ownership is out of scope.
_OWNERSHIP = re.compile(r"\sOWNER\s+TO\s", re.IGNORECASE)

# Foreign key options that only restate the default behaviour.
_DEFAULT_FK_OPTIONS = frozenset({"NOT DEFERRABLE", "INITIALLY IMMEDIATE", "MATCH SIMPLE"})

_DEFAULT_INDEX_METHODS = {Dialect.POSTGRESQL: "btree"}

# psql meta-commands such as \\restrict, which recent pg_dump versions write.
_PSQL_COMMAND = re.compile(r"^\\\S.*$", re.MULTILINE)

_IDENTIFIER = r'(?:"(?:[^"]|"")+"|[A-Za-z_][\w$]*)'
_QUALIFIED = rf"{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})*"
_SEQUENCE_OWNER = re.compile(
    rf"SEQUENCE\s+(?P<sequence>{_QUALIFIED})\s+OWNED\s+BY\s+(?P<column>{_QUALIFIED})\s*$",
    re.IGNORECASE,
)
_ADD_IDENTITY = re.compile(
    rf"TABLE\s+(?:ONLY\s+)?(?P<table>{_QUALIFIED})\s+ALTER\s+COLUMN\s+(?P<column>{_IDENTIFIER})"
    r"\s+ADD\s+GENERATED\s+(?P<kind>ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY\b",
    re.IGNORECASE,
)

_SNIPPET_LENGTH = 70


def load_ddl(sql: str, dialect: Dialect, schema: str | None = None) -> LoadResult:
    """Build a schema from DDL text written in ``dialect``.

    ``schema`` names the schema to load when the DDL qualifies object names with it, as
    ``pg_dump`` does; by default it is ``public`` in PostgreSQL.
    """
    draft = SchemaDraft(dialect, schema)
    reader = DdlReader(draft)
    reader.read(sql)
    reader.finish()
    return draft.build()


def load_ddl_file(path: Path, dialect: Dialect, schema: str | None = None) -> LoadResult:
    """Build a schema from a ``.sql`` file written in ``dialect``."""
    try:
        sql = path.read_text(encoding="utf-8")
    except OSError as error:
        raise LoadError(f"cannot read {path}: {error.strerror}") from error
    try:
        return load_ddl(sql, dialect, schema)
    except LoadError as error:
        raise LoadError(f"{path}: {error}") from error


class DdlReader:
    """Apply DDL statements to a :class:`SchemaDraft`."""

    def __init__(self, draft: SchemaDraft) -> None:
        self._draft = draft
        self._dialect = draft.dialect
        self._sqlglot = sqlglot_dialect(draft.dialect)
        # A serial column in a dump is a nextval() default on a sequence the column owns.
        self._sequences: dict[str, str] = {}
        self._sequence_defaults: dict[str, tuple[str, str]] = {}
        self._sequence_owners: dict[str, tuple[str, str]] = {}

    def read(self, sql: str) -> None:
        """Parse ``sql`` and apply each of its statements in order."""
        try:
            statements = sqlglot.parse(_PSQL_COMMAND.sub("", sql), dialect=self._sqlglot)
        except ParseError as error:
            raise LoadError(_describe_parse_error(error)) from error
        for statement in statements:
            if statement is not None:
                self._statement(self._unqualify(statement))

    def _unqualify(self, statement: exp.Expr) -> exp.Expr:
        """Drop the loaded schema from qualified names, as pg_dump writes every name.

        Names in other schemas keep their qualifier, so they are skipped or kept qualified.
        """

        def strip(node: exp.Expr) -> exp.Expr:
            if isinstance(node, exp.Table) and node.args.get("catalog") is None:
                schema = node.args.get("db")
                if isinstance(schema, exp.Identifier) and self._in_loaded_schema(schema):
                    node = node.copy()
                    node.set("db", None)
            elif (
                isinstance(node, exp.DataType)
                and isinstance(node.args.get("kind"), exp.Dot)
                and isinstance(node.args["kind"].this, exp.Identifier)
                and self._in_loaded_schema(node.args["kind"].this)
            ):
                node = node.copy()
                node.set("kind", node.args["kind"].expression)
            return node

        return statement.transform(strip)

    def finish(self) -> None:
        """Turn sequence-backed defaults into serial columns once every statement is read."""
        for sequence, (table_name, column_name) in self._sequence_defaults.items():
            if self._sequence_owners.get(sequence) != (table_name, column_name):
                continue
            table = self._draft.table(table_name)
            column = table.find_column(column_name) if table is not None else None
            if table is not None and column is not None:
                table.replace_column(replace(column, default=None, identity=Identity.SERIAL))
        for sequence, name in self._sequences.items():
            if sequence not in self._sequence_owners:
                self._draft.warn(f"skipped sequence {name!r}: sequences are not supported")

    def _statement(self, statement: exp.Expr) -> None:
        if isinstance(statement, exp.Create):
            self._create(statement)
        elif isinstance(statement, exp.Alter) and statement.args.get("kind") == "TABLE":
            self._alter_table(statement)
        elif isinstance(statement, exp.Drop):
            self._drop(statement)
        elif isinstance(statement, exp.Command):
            self._command(statement)
        elif not isinstance(statement, _IGNORED_STATEMENTS):
            self._skip(statement, "this statement is not supported")

    def _command(self, statement: exp.Command) -> None:
        """Handle statements sqlglot does not parse, of which pg_dump writes a few."""
        verb, text = statement.this.upper(), str(statement.expression).strip()
        if verb == "ALTER" and (owner := _SEQUENCE_OWNER.match(text)):
            self._own_sequence(owner["sequence"], owner["column"])
        elif verb == "ALTER" and (identity := _ADD_IDENTITY.match(text)):
            self._add_identity(statement, identity)
        elif verb in ("CREATE", "ALTER", "DROP") and not _OWNERSHIP.search(text):
            self._skip(statement, "this statement is not supported")

    def _own_sequence(self, sequence: str, column: str) -> None:
        *table, column_name = self._parts(column)
        if len(table) > 1 and not self._in_loaded_schema(exp.to_identifier(table[-2])):
            return
        if table:
            self._sequence_owners[self._sequence_key(sequence)] = (table[-1], column_name)

    def _add_identity(self, statement: exp.Command, match: re.Match[str]) -> None:
        *schema, table_name = self._parts(match["table"])
        if schema and not self._in_loaded_schema(exp.to_identifier(schema[-1])):
            return
        table = self._draft.table(table_name)
        column = table.find_column(self._parts(match["column"])[0]) if table else None
        if table is None or column is None:
            raise LoadError(f"cannot apply {_snippet(statement)}: unknown table or column")
        kind = Identity.ALWAYS if match["kind"].upper() == "ALWAYS" else Identity.BY_DEFAULT
        table.replace_column(replace(column, identity=kind, nullable=False))

    def _parts(self, qualified: str) -> list[str]:
        """Split and fold a possibly quoted, dotted name the way the database would."""
        parts = re.findall(_IDENTIFIER, qualified)
        return [
            fold_identifier(
                exp.to_identifier(part[1:-1].replace('""', '"'), quoted=True)
                if part.startswith('"')
                else exp.to_identifier(part),
                self._dialect,
            )
            for part in parts
        ]

    def _sequence_key(self, qualified: str) -> str:
        *schema, name = self._parts(qualified)
        return name_key(name, self._dialect) if len(schema) <= 1 else qualified

    def _record_sequence_default(self, table: str, column: str, default: exp.Expr) -> None:
        call = default
        if not (isinstance(call, exp.Anonymous) and str(call.this).lower() == "nextval"):
            return
        argument = call.expressions[0] if call.expressions else None
        while isinstance(argument, exp.Cast | exp.Paren):
            argument = argument.this
        if isinstance(argument, exp.Literal) and argument.is_string:
            self._sequence_defaults[self._sequence_key(argument.this)] = (table, column)

    def _create(self, statement: exp.Create) -> None:
        kind = str(statement.args.get("kind", "")).upper()
        if kind == "SEQUENCE":
            name = self._object_name(statement.this, statement)
            if name is not None:
                self._sequences[name_key(name, self._dialect)] = name
            return
        if kind == "SCHEMA":
            return
        if kind == "TABLE":
            self._create_table(statement)
        elif kind == "INDEX":
            self._create_index(statement)
        elif kind == "TYPE" and self._is_enum(statement):
            self._create_enum(statement)
        else:
            self._skip(statement, f"CREATE {kind} is not supported")

    def _create_table(self, statement: exp.Create) -> None:
        schema = statement.this
        if not isinstance(schema, exp.Schema):
            self._skip(statement, "tables created from a query are not supported")
            return
        properties = statement.args.get("properties")
        if properties is not None and properties.find(exp.TemporaryProperty):
            self._skip(statement, "temporary tables are not part of the schema")
            return
        name = self._object_name(schema.this, statement)
        if name is None:
            return
        if self._draft.table(name) is not None and statement.args.get("exists"):
            return
        table = TableDraft(name, self._dialect)
        for element in schema.expressions:
            if isinstance(element, exp.Identifier):
                # SQLite allows columns declared by name alone, without a type.
                self._add_column(table, exp.ColumnDef(this=element))
            elif isinstance(element, exp.ColumnDef):
                self._add_column(table, element)
            else:
                self._add_table_constraint(table, element)
        if properties is not None:
            self._check_table_options(table, properties)
        self._draft.add_table(table)

    def _check_table_options(self, table: TableDraft, properties: exp.Properties) -> None:
        for option in properties.expressions:
            if isinstance(option, exp.Property) and option.name == WITHOUT_ROWID:
                self._draft.warn(f"table {table.name!r}: WITHOUT ROWID is not tracked")
            elif isinstance(option, exp.StrictProperty):
                self._draft.warn(f"table {table.name!r}: STRICT is not tracked")

    def _add_column(self, table: TableDraft, definition: exp.ColumnDef) -> None:
        name = fold_identifier(definition.this, self._dialect)
        kind = definition.args.get("kind")
        data_type = DataType("")
        nullable = True
        identity: Identity | None = None
        default: exp.Expr | None = None
        if kind is not None:
            serial = serial_type(kind, self._dialect)
            if serial is not None:
                data_type, nullable, identity = serial, False, Identity.SERIAL
            else:
                data_type = canonical_type(kind, self._dialect)

        for constraint in definition.constraints:
            constraint_name = self._constraint_name(constraint)
            rule = constraint.args.get("kind")
            if isinstance(rule, exp.NotNullColumnConstraint):
                nullable = bool(rule.args.get("allow_null"))
            elif isinstance(rule, exp.DefaultColumnConstraint):
                default = rule.this
            elif isinstance(rule, exp.PrimaryKeyColumnConstraint):
                table.set_primary_key(PrimaryKey((name,), constraint_name))
            elif isinstance(rule, exp.UniqueColumnConstraint):
                table.unique_constraints.append(UniqueConstraint((name,), constraint_name))
            elif isinstance(rule, exp.CheckColumnConstraint):
                table.check_constraints.append(self._check(rule, constraint_name))
            elif isinstance(rule, exp.Reference):
                table.foreign_keys.append(self._foreign_key((name,), rule, constraint_name))
            elif isinstance(rule, exp.GeneratedAsIdentityColumnConstraint) and not rule.args.get(
                "expression"
            ):
                identity = Identity.ALWAYS if rule.this else Identity.BY_DEFAULT
                nullable = False
            elif isinstance(rule, exp.AutoIncrementColumnConstraint):
                identity = Identity.AUTOINCREMENT
            elif isinstance(rule, exp.ComputedColumnConstraint):
                self._draft.warn(
                    f"column {table.name}.{name}: generated column is treated as a regular one"
                )
            else:
                self._draft.warn(
                    f"column {table.name}.{name}: {constraint.sql(dialect=self._sqlglot)} "
                    "is not tracked"
                )

        if default is not None:
            self._record_sequence_default(table.name, name, default)
        normalized_default = (
            normalize_default(default, data_type, self._dialect) if default is not None else None
        )
        table.add_column(Column(name, data_type, nullable, normalized_default, identity))

    def _add_table_constraint(self, table: TableDraft, node: exp.Expr) -> None:
        name: str | None = None
        items = [node]
        if isinstance(node, exp.Constraint):
            name = fold_identifier(node.this, self._dialect)
            items = node.expressions
        for item in items:
            if isinstance(item, exp.PrimaryKey):
                table.set_primary_key(PrimaryKey(self._column_list(item.expressions), name))
            elif isinstance(item, exp.ForeignKey):
                columns = self._column_list(item.expressions)
                table.foreign_keys.append(
                    self._foreign_key(columns, item.args["reference"], name, item)
                )
            elif isinstance(item, exp.UniqueColumnConstraint):
                columns = self._column_list(item.this.expressions)
                table.unique_constraints.append(UniqueConstraint(columns, name))
            elif isinstance(item, exp.CheckColumnConstraint):
                table.check_constraints.append(self._check(item, name))
            else:
                self._draft.warn(
                    f"table {table.name!r}: {item.sql(dialect=self._sqlglot)} is not tracked"
                )

    def _check(self, rule: exp.CheckColumnConstraint, name: str | None) -> CheckConstraint:
        return CheckConstraint(normalize_expression(rule.this, self._dialect), name)

    def _foreign_key(
        self,
        columns: tuple[str, ...],
        reference: exp.Reference,
        name: str | None,
        node: exp.ForeignKey | None = None,
    ) -> ForeignKeyDraft:
        target = reference.this
        ref_columns: tuple[str, ...] = ()
        if isinstance(target, exp.Schema):
            ref_columns = self._column_list(target.expressions)
            target = target.this
        fk = ForeignKeyDraft(columns, self._reference_name(target), ref_columns, name=name)

        options = [str(option).upper() for option in reference.args.get("options") or ()]
        if node is not None:
            options += [
                f"ON {event.upper()} {str(node.args[event]).upper()}"
                for event in ("delete", "update")
                if node.args.get(event)
            ]
        for option in options:
            match = _REFERENTIAL_ACTION.fullmatch(option)
            if match is None:
                if option not in _DEFAULT_FK_OPTIONS:
                    self._draft.warn(
                        f"foreign key {columns} -> {fk.ref_table}: {option} is not tracked"
                    )
            elif match["event"] == "DELETE":
                fk.on_delete = ReferentialAction(match["action"])
            else:
                fk.on_update = ReferentialAction(match["action"])
        return fk

    def _create_index(self, statement: exp.Create) -> None:
        index = statement.this
        name = fold_identifier(index.this, self._dialect) if index.this else None
        table_name = self._object_name(index.args["table"], statement)
        if table_name is None:
            return
        table = self._draft.table(table_name)
        if table is None:
            raise LoadError(f"index {name!r} is created on unknown table {table_name!r}")
        if statement.args.get("exists") and any(
            existing.name == name for existing in table.indexes
        ):
            return
        params = index.args["params"]
        method = params.args.get("using")
        method_name = ascii_lower(method.name) if method is not None else None
        if method_name == _DEFAULT_INDEX_METHODS.get(self._dialect):
            method_name = None
        where = params.args.get("where")
        table.indexes.append(
            Index(
                name=name,
                elements=tuple(self._index_element(key) for key in params.args["columns"]),
                unique=bool(statement.args.get("unique")),
                where=normalize_expression(where.this, self._dialect) if where else None,
                method=method_name,
            )
        )

    def _index_element(self, key: exp.Expr) -> IndexElement:
        descending = False
        if isinstance(key, exp.Ordered):
            descending = bool(key.args.get("desc"))
            key = key.this
        inner = key.this if isinstance(key, exp.Paren) else key
        # PostgreSQL stores "(col)" as a plain column key, not as an expression.
        if isinstance(inner, exp.Column) and not inner.table:
            return IndexElement(fold_identifier(inner.this, self._dialect), descending)
        return IndexElement(normalize_expression(key, self._dialect), descending)

    def _is_enum(self, statement: exp.Create) -> bool:
        body = statement.args.get("expression")
        return isinstance(body, exp.DataType) and body.this == exp.DataType.Type.ENUM

    def _create_enum(self, statement: exp.Create) -> None:
        name = self._object_name(statement.this, statement)
        if name is None:
            return
        values = tuple(value.this for value in statement.args["expression"].expressions)
        try:
            self._draft.add_enum(EnumType(name, values))
        except ValueError as error:
            raise LoadError(str(error)) from error

    def _alter_table(self, statement: exp.Alter) -> None:
        name = self._object_name(statement.this, statement)
        if name is None:
            return
        table = self._draft.table(name)
        if table is None:
            raise LoadError(f"ALTER TABLE refers to unknown table {name!r}")
        for action in statement.args.get("actions") or ():
            handled = True
            if isinstance(action, exp.AddConstraint):
                for constraint in action.expressions:
                    self._add_table_constraint(table, constraint)
            elif isinstance(action, exp.ColumnDef):
                self._add_column(table, action)
            elif isinstance(action, exp.AlterColumn):
                handled = self._alter_column(table, action)
            else:
                handled = False
            if not handled:
                self._skip(statement, f"{action.sql(dialect=self._sqlglot)} is not supported")

    def _alter_column(self, table: TableDraft, action: exp.AlterColumn) -> bool:
        column = table.find_column(fold_identifier(action.this, self._dialect))
        if column is None:
            raise LoadError(f"ALTER COLUMN refers to unknown column {table.name}.{action.this}")
        args = action.args
        if args.get("dtype") is not None:
            return False
        if "allow_null" in args:
            column = replace(column, nullable=bool(args["allow_null"]))
        elif args.get("drop"):
            column = replace(column, default=None)
        elif args.get("default") is not None:
            self._record_sequence_default(table.name, column.name, args["default"])
            default = normalize_default(args["default"], column.type, self._dialect)
            column = replace(column, default=default)
        else:
            return False
        table.replace_column(column)
        return True

    def _drop(self, statement: exp.Drop) -> None:
        kind = str(statement.args.get("kind", "")).upper()
        for target in statement.args.get("tables") or ():
            name = self._object_name(target, statement)
            if name is None:
                continue
            if kind == "TABLE":
                self._draft.drop_table(name)
            elif kind == "INDEX":
                for table in self._draft.tables():
                    table.indexes = [index for index in table.indexes if index.name != name]
            elif kind == "TYPE":
                self._draft.drop_enum(name)
            else:
                self._skip(statement, f"DROP {kind} is not supported")

    def _object_name(self, node: exp.Expr, statement: exp.Expr) -> str | None:
        """Return the name of a schema object, or ``None`` if it lives in another schema."""
        if not isinstance(node, exp.Table):
            raise LoadError(f"cannot find the object name in {_snippet(statement)}")
        schema = node.args.get("db")
        if node.args.get("catalog") is not None or not self._in_loaded_schema(schema):
            self._skip(statement, f"only objects in schema {self._draft.schema!r} are loaded")
            return None
        return fold_identifier(node.this, self._dialect)

    def _reference_name(self, node: exp.Table) -> str:
        schema = node.args.get("db")
        name = fold_identifier(node.this, self._dialect)
        if schema is None or self._in_loaded_schema(schema):
            return name
        return f"{fold_identifier(schema, self._dialect)}.{name}"

    def _in_loaded_schema(self, schema: exp.Identifier | None) -> bool:
        if schema is None:
            return True
        name = fold_identifier(schema, self._dialect)
        return name_key(name, self._dialect) == name_key(self._draft.schema, self._dialect)

    def _column_list(self, nodes: list[exp.Expr]) -> tuple[str, ...]:
        names: list[str] = []
        for node in nodes:
            identifier = node
            while not isinstance(identifier, exp.Identifier):
                identifier = identifier.this
            names.append(fold_identifier(identifier, self._dialect))
        return tuple(names)

    def _constraint_name(self, constraint: exp.ColumnConstraint) -> str | None:
        name = constraint.args.get("this")
        return fold_identifier(name, self._dialect) if name is not None else None

    def _skip(self, statement: exp.Expr, reason: str) -> None:
        self._draft.warn(f"skipped {_snippet(statement)}: {reason}")


def _snippet(statement: exp.Expr) -> str:
    text = " ".join(statement.sql(comments=False).split())
    if len(text) > _SNIPPET_LENGTH:
        text = text[: _SNIPPET_LENGTH - 3] + "..."
    return text


def _describe_parse_error(error: ParseError) -> str:
    if not error.errors:
        return f"cannot parse SQL: {error}"
    details = error.errors[0]
    return (
        f"line {details['line']}, column {details['col']}: {details['description']} "
        f"near {details['highlight']!r}"
    )
