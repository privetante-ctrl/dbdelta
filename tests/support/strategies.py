"""Hypothesis strategies that generate valid schemas in canonical form.

Names come from small pools, so two schemas drawn one after the other share tables and
columns and differ in the details: the pairs exercise every kind of change. Schemas meant to
be migrated into each other draw from types that PostgreSQL can convert between; other types
appear only in single schemas.
"""

from collections.abc import Sequence
from dataclasses import replace

from hypothesis import strategies as st

from dbdelta.model import (
    CheckConstraint,
    Column,
    DataType,
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

TABLE_NAMES = ("t0", "t1", "t2", "t3")
COLUMN_NAMES = ("c0", "c1", "c2", "c3", "c4", "c5")

_INTEGERS = (DataType("smallint"), DataType("integer"), DataType("bigint"))
_NUMBERS = (DataType("numeric", (10, 2)), DataType("real"), DataType("double precision"))
_STRINGS = (DataType("text"), DataType("varchar", (10,)), DataType("varchar", (50,)))

CONVERTIBLE_TYPES = _INTEGERS + _NUMBERS + _STRINGS
"""Types that convert into each other, with USING where no automatic conversion exists."""

OTHER_TYPES = (DataType("boolean"), DataType("date"), DataType("timestamp"))

_DEFAULTS = {
    "smallint": ("0", "-1", "7"),
    "integer": ("0", "-1", "7"),
    "bigint": ("0", "-1", "7"),
    "numeric": ("0", "1.5"),
    "real": ("0", "1.5"),
    "double precision": ("0", "1.5"),
    "text": ("'x'", "''"),
    "varchar": ("'x'", "'it''s'"),
    "boolean": ("TRUE", "FALSE"),
    "date": (),
    "timestamp": ("CURRENT_TIMESTAMP",),
}

_ACTIONS = (ReferentialAction.NO_ACTION, ReferentialAction.CASCADE, ReferentialAction.SET_NULL)


def schemas(*, convertible: bool = False) -> st.SearchStrategy[Schema]:
    """Schemas of up to four tables with keys, constraints, indexes and foreign keys.

    The same schemas are valid in PostgreSQL and SQLite. ``convertible`` limits column types
    to those every other one converts into.
    """
    types = CONVERTIBLE_TYPES if convertible else CONVERTIBLE_TYPES + OTHER_TYPES
    return _schemas(types)


def schema_pairs() -> st.SearchStrategy[tuple[Schema, Schema]]:
    """A current and a desired schema that one migration can connect.

    The desired schema is mostly the current one with a few edits, so that migrations change
    tables in place; sometimes it is an unrelated schema.
    """
    return _pairs()


@st.composite
def _pairs(draw: st.DrawFn) -> tuple[Schema, Schema]:
    source = draw(schemas(convertible=True))
    target = draw(st.one_of(_edited(source), _edited(source), schemas(convertible=True)))
    return source, target


@st.composite
def _edited(draw: st.DrawFn, schema: Schema) -> Schema:
    tables = []
    for table in schema.tables:
        action = draw(st.sampled_from(("keep", "edit", "edit", "drop")))
        if action != "drop":
            tables.append(draw(_edited_table(table)) if action == "edit" else table)
    free = [name for name in TABLE_NAMES if schema.table(name) is None]
    if free and (not tables or draw(st.booleans())):
        tables.append(draw(_tables(draw(st.sampled_from(free)), CONVERTIBLE_TYPES)))
    return Schema(_valid_foreign_keys(tables))


@st.composite
def _edited_table(draw: st.DrawFn, table: Table) -> Table:
    key = table.primary_key.columns if table.primary_key else ()
    columns = []
    for original in table.columns:
        column = original
        match draw(st.sampled_from(("same", "same", "type", "null", "default", "drop"))):
            case "type":
                new_type = draw(st.sampled_from(CONVERTIBLE_TYPES))
                column = replace(original, type=new_type, default=None)
            case "null" if original.name not in key:
                column = replace(original, nullable=not original.nullable)
            case "default":
                defaults = _DEFAULTS[original.type.name]
                column = replace(original, default=draw(st.none() | st.sampled_from(defaults)))
            case "drop":
                continue
        columns.append(column)
    columns = columns or [table.columns[0]]
    free = [name for name in COLUMN_NAMES if table.column(name) is None]
    add_column, drop_index = draw(st.booleans()), draw(st.booleans())
    if free and add_column:
        data_type = draw(st.sampled_from(CONVERTIBLE_TYPES))
        added = Column(draw(st.sampled_from(free)), data_type, draw(st.booleans()))
        columns.insert(draw(st.integers(0, len(columns))), added)
    indexes = list(table.indexes)
    if indexes and drop_index:
        indexes.remove(draw(st.sampled_from(indexes)))
    return _valid_table(replace(table, indexes=tuple(indexes)), tuple(columns))


def _valid_table(table: Table, columns: tuple[Column, ...]) -> Table:
    """``table`` with ``columns``, keeping only the constraints that still make sense."""
    names = {column.name for column in columns}
    numeric = {column.name for column in columns if column.type in _INTEGERS + _NUMBERS}
    key = table.primary_key
    if key is not None and not set(key.columns) <= names:
        key = None
    return Table(
        table.name,
        columns,
        primary_key=key,
        foreign_keys=tuple(fk for fk in table.foreign_keys if set(fk.columns) <= names),
        unique_constraints=tuple(u for u in table.unique_constraints if set(u.columns) <= names),
        check_constraints=tuple(
            check for check in table.check_constraints if check.expression.columns <= numeric
        ),
        indexes=tuple(index for index in table.indexes if index.columns <= names),
    )


def _valid_foreign_keys(tables: list[Table]) -> tuple[Table, ...]:
    """Keep the foreign keys whose columns exist and match their referenced key's type."""
    by_name = {table.name: table for table in tables}

    def valid(table: Table, fk: ForeignKey) -> bool:
        target = by_name.get(fk.ref_table)
        column = table.column(fk.columns[0])
        if target is None or column is None or target.primary_key is None:
            return False
        key = target.column(fk.ref_columns[0])
        return (
            target.primary_key.columns == fk.ref_columns
            and key is not None
            and (key.type == column.type)
        )

    return tuple(
        replace(table, foreign_keys=tuple(fk for fk in table.foreign_keys if valid(table, fk)))
        for table in tables
    )


@st.composite
def _schemas(draw: st.DrawFn, types: Sequence[DataType]) -> Schema:
    names = draw(st.lists(st.sampled_from(TABLE_NAMES), min_size=1, max_size=4, unique=True))
    tables = [draw(_tables(name, types)) for name in names]
    keyed = {
        table.name: table.column(table.primary_key.columns[0])
        for table in tables
        if table.primary_key is not None and len(table.primary_key.columns) == 1
    }
    with_keys = []
    for table in tables:
        foreign_keys: list[ForeignKey] = []
        for column in draw(st.lists(st.sampled_from(table.columns), max_size=2, unique=True)):
            targets = [name for name, key in keyed.items() if key and key.type == column.type]
            if not targets:
                continue
            target = draw(st.sampled_from(targets))
            key = keyed[target]
            assert key is not None
            foreign_keys.append(
                ForeignKey(
                    (column.name,),
                    target,
                    (key.name,),
                    on_delete=draw(st.sampled_from(_ACTIONS)),
                )
            )
        with_keys.append(replace(table, foreign_keys=tuple(foreign_keys)))
    return Schema(tuple(with_keys))


@st.composite
def _tables(draw: st.DrawFn, name: str, types: Sequence[DataType]) -> Table:
    column_names = draw(
        st.lists(st.sampled_from(COLUMN_NAMES), min_size=1, max_size=5, unique=True)
    )
    key_columns = draw(
        st.none()
        | st.lists(st.sampled_from(column_names), min_size=1, max_size=2, unique=True).map(tuple)
    )
    columns = []
    for column_name in column_names:
        data_type = draw(st.sampled_from(types))
        defaults = _DEFAULTS[data_type.name]
        default = draw(st.none() | st.sampled_from(defaults)) if defaults else None
        # Primary key columns are always NOT NULL, which is how the loaders canonicalize them.
        nullable = key_columns is None or column_name not in key_columns
        columns.append(Column(column_name, data_type, nullable and draw(st.booleans()), default))

    unique_columns = draw(
        st.lists(
            st.lists(st.sampled_from(column_names), min_size=1, max_size=2, unique=True).map(tuple),
            max_size=2,
            unique=True,
        )
    )
    numeric = [column.name for column in columns if column.type in _INTEGERS + _NUMBERS]
    checked = draw(st.lists(st.sampled_from(numeric), max_size=2, unique=True)) if numeric else []
    indexes = [
        Index(
            f"ix_{name}_{number}",
            tuple(
                IndexElement(column, descending=draw(st.booleans()))
                for column in draw(
                    st.lists(st.sampled_from(column_names), min_size=1, max_size=2, unique=True)
                )
            ),
            unique=draw(st.booleans()),
        )
        for number in range(draw(st.integers(0, 2)))
    ]
    return Table(
        name,
        tuple(columns),
        primary_key=PrimaryKey(key_columns) if key_columns else None,
        unique_constraints=tuple(
            UniqueConstraint(key) for key in unique_columns if key != key_columns
        ),
        check_constraints=tuple(
            CheckConstraint(Expression(f'"{column}" > 0', frozenset({column})))
            for column in checked
        ),
        indexes=tuple(indexes),
    )
