"""PostgreSQL behaviour that the planner, the emitter and risk rules rely on."""

import re
from collections.abc import Sequence

from dbdelta.model import DataType, Index, Schema

MAX_NAME_BYTES = 63
"""Longest identifier PostgreSQL keeps (NAMEDATALEN - 1); longer names are truncated."""

BUILTIN_TYPES = frozenset(
    {
        "smallint",
        "integer",
        "bigint",
        "numeric",
        "real",
        "double precision",
        "money",
        "boolean",
        "text",
        "varchar",
        "char",
        "bpchar",
        "bytea",
        "date",
        "time",
        "timetz",
        "timestamp",
        "timestamptz",
        "interval",
        "uuid",
        "json",
        "jsonb",
        "xml",
        "inet",
        "cidr",
        "macaddr",
        "bit",
        "varbit",
        "tsvector",
        "tsquery",
        "oid",
    }
)

_NUMERIC_TYPES = frozenset({"smallint", "integer", "bigint", "numeric", "real", "double precision"})
_STRING_TYPES = frozenset({"text", "varchar", "char", "bpchar"})

# Pairs of date/time types converted by an assignment cast.
_DATETIME_CASTS = frozenset(
    {
        ("date", "timestamp"),
        ("date", "timestamptz"),
        ("timestamp", "timestamptz"),
        ("timestamptz", "timestamp"),
        ("timestamp", "date"),
        ("timestamptz", "date"),
        ("timestamp", "time"),
        ("timestamptz", "time"),
        ("time", "timetz"),
        ("timetz", "time"),
    }
)


def default_name(table: str, columns: Sequence[str], suffix: str) -> str:
    """Return the name PostgreSQL gives a constraint or index created without one.

    Follows ``makeObjectName`` in the PostgreSQL sources: ``table_col1_col2_suffix``, where
    the longer of the table and column parts is shortened until the name fits in 63 bytes.
    PostgreSQL appends a number when that name is already taken, which cannot be known here.
    """
    table_part = table.encode()
    column_part = "_".join(columns).encode()
    available = MAX_NAME_BYTES - len(suffix) - 1 - (1 if column_part else 0)
    table_length, column_length = len(table_part), len(column_part)
    while table_length + column_length > available:
        if table_length > column_length:
            table_length -= 1
        else:
            column_length -= 1
    parts = [_clip(table_part, table_length)]
    if column_part:
        parts.append(_clip(column_part, column_length))
    return "_".join([*parts, suffix])


def needs_explicit_cast(old: DataType, new: DataType) -> bool:
    """Tell whether ``ALTER COLUMN ... TYPE`` from ``old`` to ``new`` needs a USING clause.

    Without USING, PostgreSQL converts values with an assignment cast. Those exist between
    numeric types, to every string type, and between most date/time types; other changes,
    such as text to integer, fail unless the conversion is spelled out.
    """
    if old.is_array != new.is_array:
        return True
    if old.name == new.name or new.name in _STRING_TYPES:
        return False
    if old.name in _NUMERIC_TYPES and new.name in _NUMERIC_TYPES:
        return False
    return (old.name, new.name) not in _DATETIME_CASTS


# Type changes PostgreSQL makes without rewriting the table when the new type modifier is
# larger or absent (see "ALTER TABLE ... SET DATA TYPE" in the PostgreSQL documentation).
_WIDENED_IN_PLACE = frozenset(
    {"varchar", "varbit", "time", "timetz", "timestamp", "timestamptz", "interval"}
)
_TEXT_TYPES = frozenset({"text", "varchar"})

# Functions whose result differs per row; a column default calling one must be computed
# for every existing row when the column is added.
_VOLATILE_CALL = re.compile(
    r"\b(random|clock_timestamp|timeofday|gen_random_uuid|uuid_generate_v[14]|nextval)\s*\(",
    re.IGNORECASE,
)


_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def rewrites_table(old: DataType, new: DataType) -> bool:
    """Tell whether ``ALTER COLUMN ... TYPE`` rewrites the whole table and its indexes.

    PostgreSQL only skips the rewrite when the old values are valid in the new type as they
    are: a varchar or time precision that grows or goes away, a numeric precision that grows
    with the same scale, or a switch between text and unbounded varchar. Arrays are always
    rewritten when their element type changes, because every array stores that type.
    ``timestamp`` to ``timestamptz`` counts as a rewrite; PostgreSQL 12+ skips it only when
    the session time zone is UTC.
    """
    if old.is_array != new.is_array:
        return True
    if old.name == new.name:
        return _narrows_modifier(old, new)
    if old.is_array:
        return True
    return not (old.name in _TEXT_TYPES and new.name in _TEXT_TYPES and not new.params)


def backs_foreign_key(schema: Schema, table: str, index: Index) -> bool:
    """Tell whether a foreign key in ``schema`` relies on the unique index ``index``."""
    if not index.unique or index.where is not None:
        return False
    columns = frozenset(str(element.key) for element in index.elements)
    return any(
        fk.ref_table == table and frozenset(fk.ref_columns) == columns
        for candidate in schema.tables
        for fk in candidate.foreign_keys
    )


def has_volatile_default(default: str) -> bool:
    """Tell whether a default calls a function whose value changes from row to row."""
    return _VOLATILE_CALL.search(_STRING_LITERAL.sub("''", default)) is not None


def is_builtin(data_type: DataType) -> bool:
    """Tell a built-in type from a user-defined one such as an enum type."""
    return data_type.name in BUILTIN_TYPES


def _clip(text: bytes, length: int) -> str:
    # Cutting at a byte count may split a multi-byte character; drop the partial character.
    return text[:length].decode("utf-8", errors="ignore")


def _narrows_modifier(old: DataType, new: DataType) -> bool:
    if not new.params:
        return bool(old.params) and old.name not in _WIDENED_IN_PLACE | {"numeric"}
    if not old.params:
        return True
    if old.name == "numeric":
        old_precision, old_scale = old.params
        new_precision, new_scale = new.params
        return new_scale != old_scale or new_precision < old_precision
    return old.name not in _WIDENED_IN_PLACE or new.params[0] < old.params[0]
