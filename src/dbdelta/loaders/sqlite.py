"""Load the schema of a live SQLite database.

SQLite exposes the structure of a table through its catalog: column types, nullability,
defaults and key columns, as parsed by SQLite itself. The loader reads that structure
through SQLAlchemy, which makes it an independent check on dbdelta's DDL parser.

Some definitions exist only as text in the DDL that SQLite stores in ``sqlite_master``:
constraint names, CHECK conditions, index expressions and partial index predicates, and
the ``AUTOINCREMENT`` keyword. The loader takes those from that stored DDL, parsed by the
same reader as schema files. The SQLAlchemy inspector is not used for them because it
skips expression indexes, drops referential actions of unnamed foreign keys and misses
UNIQUE constraints whose column names differ in case from the column declaration.
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import Connection, Inspector, inspect, text
from sqlalchemy.exc import OperationalError

from dbdelta.dialects import Dialect
from dbdelta.loaders._draft import ForeignKeyDraft, SchemaDraft, TableDraft
from dbdelta.loaders.base import LoadError, LoadResult
from dbdelta.loaders.ddl import DdlReader
from dbdelta.loaders.normalize import parse_default, parse_type
from dbdelta.loaders.types import ascii_lower
from dbdelta.model import Column, PrimaryKey, ReferentialAction, UniqueConstraint

_SQLITE = Dialect.SQLITE

# pragma_table_xinfo marks generated columns with these values of "hidden".
_GENERATED_COLUMN = frozenset({2, 3})

_Names = tuple[str, ...]


def load_sqlite(connection: Connection) -> LoadResult:
    """Read the schema of the SQLite database behind ``connection``."""
    draft = SchemaDraft(_SQLITE)
    tables = _table_names(connection, draft)
    stored = _stored_ddl(connection, tables)
    draft.warnings.extend(stored.warnings)
    inspector = inspect(connection)
    for name in tables:
        stored_table = stored.table(name)
        if stored_table is None:
            raise LoadError(f"cannot find the definition of table {name!r} in sqlite_master")
        draft.add_table(_reflect_table(connection, inspector, draft, name, stored_table))
    return draft.build()


def _table_names(connection: Connection, draft: SchemaDraft) -> list[str]:
    """List ordinary tables, leaving out virtual tables and the shadow tables behind them."""
    try:
        rows = connection.execute(
            text(
                "SELECT name, type FROM pragma_table_list"
                " WHERE schema = 'main' AND name NOT LIKE 'sqlite~_%' ESCAPE '~' ORDER BY name"
            )
        ).tuples()
    except OperationalError as error:
        raise LoadError("reading a live database requires SQLite 3.37 or newer") from error
    tables = []
    for name, kind in rows:
        if kind == "table":
            tables.append(name)
        elif kind == "virtual":
            draft.warn(f"skipped virtual table {name!r}: virtual tables are not supported")
    return tables


def _stored_ddl(connection: Connection, tables: list[str]) -> SchemaDraft:
    """Parse the DDL that SQLite keeps for the tables and their explicitly created indexes."""
    rows = connection.execute(
        text(
            "SELECT tbl_name, sql FROM sqlite_master"
            " WHERE type IN ('table', 'index') AND sql IS NOT NULL"
            " ORDER BY type = 'index', name"
        )
    ).tuples()
    stored = SchemaDraft(_SQLITE)
    reader = DdlReader(stored)
    wanted = set(tables)
    for table, sql in rows:
        if table in wanted:
            reader.read(sql)
    return stored


def _reflect_table(
    connection: Connection,
    inspector: Inspector,
    draft: SchemaDraft,
    name: str,
    stored: TableDraft,
) -> TableDraft:
    table = TableDraft(name, _SQLITE)
    declared_types = {
        row.name: row
        for row in connection.execute(
            text("SELECT name, type, hidden FROM pragma_table_xinfo(:table)"), {"table": name}
        )
    }
    for reflected in inspector.get_columns(name):
        info = declared_types[reflected["name"]]
        if info.hidden in _GENERATED_COLUMN:
            draft.warn(f"column {name}.{info.name}: generated column is treated as a regular one")
        column_type = parse_type(info.type, _SQLITE)
        default = reflected.get("default")
        stored_column = stored.find_column(reflected["name"])
        table.add_column(
            Column(
                name=reflected["name"],
                type=column_type,
                nullable=reflected["nullable"],
                default=parse_default(default, column_type, _SQLITE) if default else None,
                identity=stored_column.identity if stored_column is not None else None,
            )
        )

    key_columns = tuple(inspector.get_pk_constraint(name)["constrained_columns"])
    if key_columns:
        stored_key = stored.primary_key
        candidates = [(stored_key.columns, stored_key.name)] if stored_key is not None else []
        table.set_primary_key(PrimaryKey(key_columns, _stored_name(candidates, key_columns)))

    table.foreign_keys.extend(_foreign_keys(connection, name, stored))
    stored_uniques = [(unique.columns, unique.name) for unique in stored.unique_constraints]
    table.unique_constraints.extend(
        UniqueConstraint(columns, _stored_name(stored_uniques, columns))
        for columns in _unique_constraint_columns(connection, name)
    )
    table.check_constraints.extend(stored.check_constraints)
    table.indexes.extend(stored.indexes)
    return table


def _foreign_keys(connection: Connection, table: str, stored: TableDraft) -> list[ForeignKeyDraft]:
    rows = connection.execute(
        text(
            'SELECT id, "from", "table", "to", on_update, on_delete'
            " FROM pragma_foreign_key_list(:table) ORDER BY id, seq"
        ),
        {"table": table},
    )
    grouped: dict[int, list[tuple[str, str, str | None, str, str]]] = defaultdict(list)
    for fk_id, column, ref_table, ref_column, on_update, on_delete in rows.tuples():
        grouped[fk_id].append((column, ref_table, ref_column, on_update, on_delete))

    stored_names = [((*fk.columns, fk.ref_table), fk.name) for fk in stored.foreign_keys]
    foreign_keys = []
    for parts in grouped.values():
        _, ref_table, _, on_update, on_delete = parts[0]
        columns = tuple(part[0] for part in parts)
        # "to" is NULL when the foreign key implicitly references the primary key.
        ref_columns = tuple(part[2] for part in parts if part[2] is not None)
        foreign_keys.append(
            ForeignKeyDraft(
                columns=columns,
                ref_table=ref_table,
                ref_columns=ref_columns if len(ref_columns) == len(columns) else (),
                on_delete=ReferentialAction(on_delete),
                on_update=ReferentialAction(on_update),
                name=_stored_name(stored_names, (*columns, ref_table)),
            )
        )
    return foreign_keys


def _unique_constraint_columns(connection: Connection, table: str) -> list[_Names]:
    # SQLite backs every UNIQUE constraint with an automatic index of origin "u".
    indexes = connection.execute(
        text("SELECT name FROM pragma_index_list(:table) WHERE origin = 'u' ORDER BY name"),
        {"table": table},
    ).scalars()
    return [
        tuple(
            connection.execute(
                text("SELECT name FROM pragma_index_info(:index) ORDER BY seqno"),
                {"index": index},
            ).scalars()
        )
        for index in indexes
    ]


def _stored_name(candidates: Iterable[tuple[_Names, str | None]], key: _Names) -> str | None:
    """Find the declared name of the constraint identified by ``key`` in the stored DDL."""
    wanted = tuple(ascii_lower(part) for part in key)
    return next(
        (
            name
            for candidate, name in candidates
            if tuple(ascii_lower(part) for part in candidate) == wanted
        ),
        None,
    )
