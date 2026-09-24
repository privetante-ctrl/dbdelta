"""Load the schema of a live PostgreSQL database.

Columns, keys, UNIQUE and CHECK constraints, foreign keys and enum types come from the
SQLAlchemy inspector. The catalog is queried directly for what the inspector reports only
approximately: exact column types (``format_type``), whether a column is a ``serial``
(a default of ``nextval`` on a sequence the column owns), index definitions
(``pg_get_indexdef``, parsed by the same reader as schema files) and row estimates.

The connection's search path is set to the loaded schema, so PostgreSQL prints type,
sequence and table names without a schema prefix, exactly as a schema file names them.
"""

from sqlalchemy import Connection, Inspector, inspect, text
from sqlalchemy.dialects.postgresql.base import PGInspector

from dbdelta.dialects import Dialect
from dbdelta.loaders._draft import ForeignKeyDraft, SchemaDraft, TableDraft
from dbdelta.loaders.base import LoadError, LoadResult
from dbdelta.loaders.ddl import DdlReader
from dbdelta.loaders.normalize import parse_default, parse_expression, parse_type
from dbdelta.model import (
    CheckConstraint,
    Column,
    EnumType,
    Identity,
    PrimaryKey,
    ReferentialAction,
    UniqueConstraint,
)

_PG = Dialect.POSTGRESQL

_RELATION_KINDS = {
    "v": "view",
    "m": "materialized view",
    "p": "partitioned table",
    "f": "foreign table",
}

_COLUMNS = text(
    """
    SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
           a.attidentity = '' AND pg_get_serial_sequence(
               format('%I.%I', n.nspname, c.relname), a.attname) IS NOT NULL
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relkind = 'r' AND NOT c.relispartition
      AND a.attnum > 0 AND NOT a.attisdropped
    """
)

_RELATIONS = text(
    """
    SELECT c.relname, c.relkind, c.reltuples, c.relispartition
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relkind IN ('r', 'v', 'm', 'p', 'f')
    ORDER BY c.relname
    """
)

# Indexes that back a primary key, UNIQUE or exclusion constraint belong to the constraint.
_INDEXES = text(
    """
    SELECT pg_get_indexdef(i.indexrelid)
    FROM pg_index i
    JOIN pg_class t ON t.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = :schema AND t.relkind = 'r' AND NOT t.relispartition
      AND NOT EXISTS (
          SELECT 1 FROM pg_constraint con
          WHERE con.conindid = i.indexrelid AND con.contype IN ('p', 'u', 'x'))
    ORDER BY 1
    """
)


def load_postgresql(connection: Connection, schema: str = "public") -> LoadResult:
    """Read the tables and enum types of ``schema`` through ``connection``."""
    found = connection.execute(
        text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"), {"schema": schema}
    ).first()
    if found is None:
        raise LoadError(f"schema {schema!r} does not exist")
    connection.execute(
        text("SELECT set_config('search_path', quote_ident(:schema), false)"), {"schema": schema}
    )
    draft = SchemaDraft(_PG, schema)
    inspector = inspect(connection)
    if not isinstance(inspector, PGInspector):
        raise LoadError("the connection does not lead to a PostgreSQL database")

    tables: list[str] = []
    estimates: dict[str, int] = {}
    for name, kind, rows, is_partition in connection.execute(_RELATIONS, {"schema": schema}):
        if kind == "r" and not is_partition:
            tables.append(name)
            # reltuples is -1 until the table has been vacuumed or analyzed.
            if rows >= 0:
                estimates[name] = int(rows)
        elif kind in _RELATION_KINDS and not is_partition:
            draft.warn(f"skipped {_RELATION_KINDS[kind]} {name!r}: it is not supported")

    for enum in inspector.get_enums(schema=schema):
        draft.add_enum(EnumType(enum["name"], tuple(enum["labels"])))

    column_facts: dict[tuple[str, str], tuple[str, bool]] = {
        (table, name): (type_text, bool(owns_sequence))
        for table, name, type_text, owns_sequence in connection.execute(
            _COLUMNS, {"schema": schema}
        )
    }
    for table in tables:
        draft.add_table(_reflect_table(inspector, draft, schema, table, column_facts))

    reader = DdlReader(draft)
    for (definition,) in connection.execute(_INDEXES, {"schema": schema}):
        reader.read(definition)
    result = draft.build()
    return LoadResult(result.schema, result.warnings, estimates)


def _reflect_table(
    inspector: Inspector,
    draft: SchemaDraft,
    schema: str,
    name: str,
    column_facts: dict[tuple[str, str], tuple[str, bool]],
) -> TableDraft:
    table = TableDraft(name, _PG)
    for reflected in inspector.get_columns(name, schema=schema):
        type_text, owns_sequence = column_facts[(name, reflected["name"])]
        column_type = parse_type(type_text, _PG)
        default = _unqualify_sequence(reflected.get("default"), schema)
        identity: Identity | None = None
        if reflected.get("identity"):
            identity = Identity.ALWAYS if reflected["identity"]["always"] else Identity.BY_DEFAULT
        elif owns_sequence and default is not None and default.startswith("nextval("):
            identity, default = Identity.SERIAL, None
        table.add_column(
            Column(
                name=reflected["name"],
                type=column_type,
                nullable=reflected["nullable"],
                default=parse_default(default, column_type, _PG) if default else None,
                identity=identity,
            )
        )

    key = inspector.get_pk_constraint(name, schema=schema)
    if key["constrained_columns"]:
        table.set_primary_key(PrimaryKey(tuple(key["constrained_columns"]), key.get("name")))

    for fk in inspector.get_foreign_keys(name, schema=schema):
        options = fk.get("options") or {}
        if options.get("deferrable") or options.get("match"):
            draft.warn(
                f"foreign key {fk['name']!r} of {name!r}: DEFERRABLE and MATCH are not tracked"
            )
        referred = fk["referred_table"]
        if fk.get("referred_schema") not in (None, schema):
            referred = f"{fk['referred_schema']}.{referred}"
        table.foreign_keys.append(
            ForeignKeyDraft(
                columns=tuple(fk["constrained_columns"]),
                ref_table=referred,
                ref_columns=tuple(fk["referred_columns"]),
                on_delete=ReferentialAction(options.get("ondelete", "NO ACTION").upper()),
                on_update=ReferentialAction(options.get("onupdate", "NO ACTION").upper()),
                name=fk.get("name"),
            )
        )

    for unique in inspector.get_unique_constraints(name, schema=schema):
        if (unique.get("dialect_options") or {}).get("postgresql_nulls_not_distinct"):
            draft.warn(f"unique constraint {unique['name']!r}: NULLS NOT DISTINCT is not tracked")
        table.unique_constraints.append(
            UniqueConstraint(tuple(unique["column_names"]), unique.get("name"))
        )
    for check in inspector.get_check_constraints(name, schema=schema):
        table.check_constraints.append(
            CheckConstraint(parse_expression(check["sqltext"], _PG), check.get("name"))
        )
    return table


def _unqualify_sequence(default: str | None, schema: str) -> str | None:
    """Undo the schema SQLAlchemy writes into ``nextval('sequence')`` defaults.

    PostgreSQL prints the sequence unqualified because it is on the search path; the
    inspector adds ``"schema".`` regardless, which a schema file never has.
    """
    prefix = f'nextval(\'"{schema}".'
    if default is not None and default.startswith(prefix):
        return "nextval('" + default.removeprefix(prefix)
    return default
