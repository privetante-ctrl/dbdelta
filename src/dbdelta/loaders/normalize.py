"""Canonical forms of types, defaults and expressions, shared by every loader.

A file and a live database describe the same schema with different spellings: PostgreSQL
reports ``DEFAULT 'x'`` as ``'x'::text`` and ``DEFAULT -1`` as ``'-1'::integer``, SQLite
returns defaults without the parentheses they were declared with. Each loader passes raw
SQL through these functions so that the diff only ever sees canonical values.
"""

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

from dbdelta.dialects import Dialect
from dbdelta.loaders._sqlglot import sqlglot_dialect
from dbdelta.loaders.base import LoadError
from dbdelta.loaders.types import canonical_type
from dbdelta.model import DataType, Expression

_TRUE_WORDS = frozenset({"t", "true", "y", "yes", "on", "1"})
_FALSE_WORDS = frozenset({"f", "false", "n", "no", "off", "0"})

_NUMERIC_TYPES = frozenset(
    {"smallint", "integer", "bigint", "numeric", "real", "double precision", "tinyint"}
)

# PostgreSQL reports casts to char(n) columns as casts to its internal name bpchar.
_CAST_ALIASES = {"bpchar": "char"}

_NUMBER = re.compile(r"-?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?")
_WHITESPACE = re.compile(r"\s+")


def parse_type(text: str, dialect: Dialect) -> DataType:
    """Canonicalize a type name as reported by a database catalog."""
    try:
        cast = sqlglot.parse_one(f"CAST(NULL AS {text})", dialect=sqlglot_dialect(dialect))
    except SqlglotError:
        cast = None
    if isinstance(cast, exp.Cast):
        return canonical_type(cast.to, dialect)
    # Free-form SQLite type names like "UNSIGNED BIG INT" are not valid in a CAST.
    return DataType(_WHITESPACE.sub(" ", text.strip()).lower())


def parse_expression(text: str, dialect: Dialect) -> Expression:
    """Canonicalize a SQL expression such as a CHECK condition."""
    return normalize_expression(_parse(text, dialect), dialect)


def parse_default(text: str, column_type: DataType, dialect: Dialect) -> str | None:
    """Canonicalize a column default; ``None`` means the column has no default."""
    return normalize_default(_parse(text, dialect), column_type, dialect)


def normalize_expression(node: exp.Expr, dialect: Dialect) -> Expression:
    """Render a parsed expression canonically and collect the columns it reads.

    Identifiers are folded the way the database folds them and then always quoted, so
    ``"age" > 0``, ``AGE > 0`` and ``(age > 0)`` all become ``"age" > 0`` in PostgreSQL.
    Quoting everything keeps the output valid without tracking each dialect's keywords.
    """
    sg_dialect = sqlglot_dialect(dialect)
    node = normalize_identifiers(_unwrap(node.copy()), dialect=sg_dialect)
    for identifier in node.find_all(exp.Identifier):
        identifier.set("quoted", True)
    columns = frozenset(column.name for column in node.find_all(exp.Column))
    return Expression(node.sql(dialect=sg_dialect), columns)


def normalize_default(node: exp.Expr, column_type: DataType, dialect: Dialect) -> str | None:
    """Canonicalize a column default for a column of ``column_type``."""
    node = _unwrap(node)
    if isinstance(node, exp.Cast) and _same_base_type(node.to, column_type, dialect):
        node = _unwrap(node.this)
    if isinstance(node, exp.Null):
        return None
    return normalize_expression(_coerce_literal(node, column_type), dialect).sql


def _parse(text: str, dialect: Dialect) -> exp.Expr:
    try:
        node = sqlglot.parse_one(text, dialect=sqlglot_dialect(dialect))
    except SqlglotError as error:
        raise LoadError(f"cannot parse expression {text!r}: {error}") from error
    if node is None:
        raise LoadError(f"cannot parse expression {text!r}")
    return node


def _unwrap(node: exp.Expr) -> exp.Expr:
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def _same_base_type(cast_to: exp.DataType, column_type: DataType, dialect: Dialect) -> bool:
    target = canonical_type(cast_to, dialect)
    name = _CAST_ALIASES.get(target.name, target.name)
    return name == column_type.name and target.is_array == column_type.is_array


def _coerce_literal(node: exp.Expr, column_type: DataType) -> exp.Expr:
    """Replace a literal by the literal the column type turns it into."""
    if column_type.is_array:
        return node
    literal = node.this if isinstance(node, exp.Neg) else node
    if not isinstance(literal, exp.Literal):
        return node
    text = literal.this if node is literal else f"-{literal.this}"
    if column_type.name == "boolean":
        if text.lower() in _TRUE_WORDS:
            return exp.true()
        if text.lower() in _FALSE_WORDS:
            return exp.false()
    if column_type.name in _NUMERIC_TYPES and literal.is_string and _NUMBER.fullmatch(text):
        return exp.Literal.number(text)
    return node
