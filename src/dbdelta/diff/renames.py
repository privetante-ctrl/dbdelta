"""Tell renames from a drop and an add, and apply renames to a schema.

A diff only sees names: a renamed column shows up as one column dropped and another added,
which as a migration loses the column's data. A dropped and an added object of the same
shape are therefore reported as a possible rename, with a confidence from 0 to 1 built from
how similar their names are (``difflib``) and how much of their shape matches. Nothing is
renamed unless the caller asks for it.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from dbdelta.dialects import Dialect, ascii_lower, name_key
from dbdelta.dialects.postgresql import name_implicit_objects
from dbdelta.dialects.quoting import quote_identifier
from dbdelta.diff.changes import (
    AddColumn,
    AddTable,
    Change,
    DropColumn,
    DropTable,
    RenameChange,
    RenameColumn,
    RenameTable,
)
from dbdelta.model import CheckConstraint, Expression, Index, Schema, Table

RENAME_CONFIDENCE = 0.6
"""Pairs below this confidence are not considered renames."""

_MIN_SHARED_COLUMNS = 0.5
"""Tables sharing fewer of their columns than this are never renames of each other."""


@dataclass(frozen=True, slots=True)
class PossibleRename:
    """A dropped and an added object that may be the same object under a new name."""

    rename: RenameChange
    confidence: float
    dropped: DropTable | DropColumn
    added: AddTable | AddColumn


def possible_renames(changes: Sequence[Change]) -> tuple[PossibleRename, ...]:
    """Pair dropped tables and columns with added ones that look like their renames.

    A column pairs with a column of the same type in the same table; a table pairs with a
    table sharing at least half of its columns. Each object belongs to at most one pair,
    the most confident first. Confidence does not depend on which side is the source, so
    the renames of a down migration are the reverse of those of the up migration.
    """
    candidates = sorted(
        [*_table_candidates(changes), *_column_candidates(changes)],
        key=lambda candidate: (-round(candidate.confidence, 9), _pair_key(candidate)),
    )
    used: set[Change] = set()
    chosen = []
    for candidate in candidates:
        if candidate.dropped in used or candidate.added in used:
            continue
        used |= {candidate.dropped, candidate.added}
        chosen.append(candidate)
    return tuple(chosen)


def apply_renames(schema: Schema, changes: Iterable[Change], dialect: Dialect) -> Schema:
    """``schema`` as it is after the table and column renames among ``changes`` ran.

    The database carries a rename through to everything that refers to the old name: keys,
    indexes, CHECK conditions and foreign keys of other tables. Names that the database
    derived from the old names when it created a constraint stay as they were.
    """
    changes = list(changes)
    for change in changes:
        if isinstance(change, RenameTable):
            schema = _rename_table(schema, change, dialect)
    for change in changes:
        if isinstance(change, RenameColumn):
            schema = _rename_column(schema, change, dialect)
    return schema


def names_before_renames(sql: str, changes: Iterable[Change], dialect: Dialect) -> str | None:
    """Rewrite ``sql``, which uses the names after the renames among ``changes``, with the
    names before them, so that it can run before the migration.

    ``sql`` must quote every table and column name, as the risk rules' queries do. A new
    column name is mapped back only when its table's new name appears in ``sql``. ``None``
    means that a name could be meant in more than one way.
    """
    changes = list(changes)
    tables = {
        name_key(change.new_name, dialect): change.table
        for change in changes
        if isinstance(change, RenameTable)
    }
    tokens = list(_tokens(sql))
    mentioned = {name_key(_unquote(token), dialect) for token, quoted in tokens if quoted}
    columns: dict[str, set[str]] = {}
    for change in changes:
        if isinstance(change, RenameColumn) and name_key(change.table, dialect) in mentioned:
            columns.setdefault(name_key(change.new_name, dialect), set()).add(change.column)
    parts = []
    for token, quoted in tokens:
        key = name_key(_unquote(token), dialect) if quoted else None
        table, column = tables.get(key or ""), columns.get(key or "", set())
        if (table and column) or len(column) > 1:
            return None
        if table:
            parts.append(quote_identifier(table))
        elif column:
            parts.append(quote_identifier(next(iter(column))))
        else:
            parts.append(token)
    return "".join(parts)


def _unquote(token: str) -> str:
    return token[1:-1].replace('""', '"')


def _column_candidates(changes: Sequence[Change]) -> Iterator[PossibleRename]:
    dropped = [change for change in changes if isinstance(change, DropColumn)]
    added = [change for change in changes if isinstance(change, AddColumn)]
    for drop in dropped:
        for add in added:
            old, new = drop.column, add.column
            if drop.table != add.table or old.type != new.type:
                continue
            same = (
                old.nullable == new.nullable,
                old.default == new.default,
                old.identity == new.identity,
            )
            confidence = 0.6 * _similarity(old.name, new.name) + 0.4 * sum(same) / len(same)
            if confidence >= RENAME_CONFIDENCE:
                rename = RenameColumn(drop.table, old.name, new.name)
                yield PossibleRename(rename, confidence, drop, add)


def _table_candidates(changes: Sequence[Change]) -> Iterator[PossibleRename]:
    dropped = [change for change in changes if isinstance(change, DropTable)]
    added = [change for change in changes if isinstance(change, AddTable)]
    for drop in dropped:
        for add in added:
            shared = _shared_columns(drop.table, add.table)
            if shared < _MIN_SHARED_COLUMNS:
                continue
            confidence = 0.4 * _similarity(drop.table.name, add.table.name) + 0.6 * shared
            if confidence >= RENAME_CONFIDENCE:
                rename = RenameTable(drop.table.name, add.table.name)
                yield PossibleRename(rename, confidence, drop, add)


def _similarity(old: str, new: str) -> float:
    old, new = ascii_lower(old), ascii_lower(new)
    # SequenceMatcher is not exactly symmetric; taking both orders makes it so.
    return max(SequenceMatcher(None, old, new).ratio(), SequenceMatcher(None, new, old).ratio())


def _shared_columns(old: Table, new: Table) -> float:
    """Share of the columns, by name and type, that both tables have (Jaccard index)."""
    old_columns = {(ascii_lower(column.name), column.type) for column in old.columns}
    new_columns = {(ascii_lower(column.name), column.type) for column in new.columns}
    return len(old_columns & new_columns) / len(old_columns | new_columns)


def _pair_key(candidate: PossibleRename) -> tuple[str, ...]:
    rename = candidate.rename
    if isinstance(rename, RenameTable):
        return ("", *sorted((rename.table, rename.new_name)))
    return (rename.table, *sorted((rename.column, rename.new_name)))


def _rename_table(schema: Schema, rename: RenameTable, dialect: Dialect) -> Schema:
    old_key = name_key(_find(schema, rename.table, dialect).name, dialect)

    def update(table: Table) -> Table:
        if name_key(table.name, dialect) == old_key:
            table = replace(_pin_names(table, dialect), name=rename.new_name)
        return replace(
            table,
            foreign_keys=tuple(
                replace(fk, ref_table=rename.new_name)
                if name_key(fk.ref_table, dialect) == old_key
                else fk
                for fk in table.foreign_keys
            ),
        )

    return replace(schema, tables=tuple(update(table) for table in schema.tables))


def _rename_column(schema: Schema, rename: RenameColumn, dialect: Dialect) -> Schema:
    owner = _find(schema, rename.table, dialect)
    table_key, old = name_key(owner.name, dialect), rename.column

    def renamed(column: str) -> str:
        return rename.new_name if name_key(column, dialect) == name_key(old, dialect) else column

    def names(columns: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(renamed(column) for column in columns)

    def expression(value: Expression) -> Expression:
        return _rename_in_expression(value, old, rename.new_name, dialect)

    def index(value: Index) -> Index:
        elements = tuple(
            replace(
                element,
                key=renamed(element.key)
                if isinstance(element.key, str)
                else expression(element.key),
            )
            for element in value.elements
        )
        where = expression(value.where) if value.where is not None else None
        return replace(value, elements=elements, where=where)

    def update(table: Table) -> Table:
        foreign_keys = tuple(
            replace(fk, ref_columns=names(fk.ref_columns))
            if name_key(fk.ref_table, dialect) == table_key
            else fk
            for fk in table.foreign_keys
        )
        if name_key(table.name, dialect) != table_key:
            return replace(table, foreign_keys=foreign_keys)
        table = _pin_names(replace(table, foreign_keys=foreign_keys), dialect)
        key = table.primary_key
        return replace(
            table,
            columns=tuple(replace(column, name=renamed(column.name)) for column in table.columns),
            primary_key=replace(key, columns=names(key.columns)) if key else None,
            foreign_keys=tuple(replace(fk, columns=names(fk.columns)) for fk in foreign_keys),
            unique_constraints=tuple(
                replace(unique, columns=names(unique.columns))
                for unique in table.unique_constraints
            ),
            check_constraints=tuple(
                CheckConstraint(expression(check.expression), check.name)
                for check in table.check_constraints
            ),
            indexes=tuple(index(value) for value in table.indexes),
        )

    return replace(schema, tables=tuple(update(table) for table in schema.tables))


def _pin_names(table: Table, dialect: Dialect) -> Table:
    # PostgreSQL named the constraints of this table after the old names, and a rename
    # keeps those names; without pinning them, the emitter would derive them anew.
    return name_implicit_objects(table) if dialect is Dialect.POSTGRESQL else table


def _find(schema: Schema, name: str, dialect: Dialect) -> Table:
    key = name_key(name, dialect)
    for table in schema.tables:
        if name_key(table.name, dialect) == key:
            return table
    raise ValueError(f"cannot rename {name!r}: the schema has no such table")


def _rename_in_expression(
    expression: Expression, old: str, new: str, dialect: Dialect
) -> Expression:
    """Replace the quoted identifier ``old`` by ``new``, leaving string literals alone."""
    old_key = name_key(old, dialect)
    parts = [
        quote_identifier(new)
        if is_identifier and name_key(_unquote(token), dialect) == old_key
        else token
        for token, is_identifier in _tokens(expression.sql)
    ]
    columns = frozenset(
        new if name_key(column, dialect) == old_key else column for column in expression.columns
    )
    return Expression("".join(parts), columns)


def _tokens(sql: str) -> Iterator[tuple[str, bool]]:
    """Split canonical SQL into quoted identifiers, string literals and everything else."""
    start = position = 0
    while position < len(sql):
        quote = sql[position]
        if quote not in "\"'":
            position += 1
            continue
        if start < position:
            yield sql[start:position], False
        end = position + 1
        while end < len(sql):
            if sql[end] == quote:
                if sql[end + 1 : end + 2] != quote:
                    break
                end += 1
            end += 1
        yield sql[position : end + 1], quote == '"'
        start = position = end + 1
    if start < len(sql):
        yield sql[start:], False
