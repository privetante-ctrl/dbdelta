"""Canonical forms of types, defaults and expressions, shared by every loader.

A file and a live database describe the same schema with different spellings: PostgreSQL
reports ``DEFAULT 'x'`` as ``'x'::text`` and ``DEFAULT -1`` as ``'-1'::integer``, SQLite
returns defaults without the parentheses they were declared with. Each loader passes raw
SQL through these functions so that the diff only ever sees canonical values.
"""

import re
from collections.abc import Callable

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

_STRING_TYPES = frozenset({"text", "varchar", "char"})

# Casting a string literal to these types keeps its value unchanged.
_LOSSLESS_STRING_CASTS = frozenset({DataType("text"), DataType("varchar")})

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


def normalize_expression(
    node: exp.Expr, dialect: Dialect, *, implicit_casts: bool = True
) -> Expression:
    """Render a parsed expression canonically and collect the columns it reads.

    Identifiers are folded the way the database folds them and then always quoted, so
    ``"age" > 0``, ``AGE > 0`` and ``(age > 0)`` all become ``"age" > 0`` in PostgreSQL.
    Quoting everything keeps the output valid without tracking each dialect's keywords.

    PostgreSQL prints stored conditions in its own way: with redundant parentheses, with
    casts it added itself (``0::numeric``, ``status::text``) and with ``IN`` lists turned into
    ``= ANY (ARRAY[...])``. Those spellings are folded back, so a condition compares equal
    whether it was read from a file or from the catalog. ``implicit_casts=False`` keeps all
    casts, for defaults, where a cast may change the stored value.
    """
    sg_dialect = sqlglot_dialect(dialect)
    node = normalize_identifiers(_unwrap(node.copy()), dialect=sg_dialect)
    if implicit_casts:
        node = _rewrite(node, _drop_implicit_cast)
        node = _rewrite(node, _any_to_in)
    node = _unwrap(_rewrite(node, _drop_redundant_paren))
    for identifier in node.find_all(exp.Identifier):
        identifier.set("quoted", True)
    columns = frozenset(column.name for column in node.find_all(exp.Column))
    return Expression(node.sql(dialect=sg_dialect), columns)


def normalize_default(node: exp.Expr, column_type: DataType, dialect: Dialect) -> str | None:
    """Canonicalize a column default for a column of ``column_type``."""
    node = _unwrap(node)
    if isinstance(node, exp.Cast) and _cast_is_redundant(node, column_type, dialect):
        node = _unwrap(node.this)
    if isinstance(node, exp.Null):
        return None
    literal = _coerce_literal(node, column_type)
    return normalize_expression(literal, dialect, implicit_casts=False).sql


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


def _cast_is_redundant(cast: exp.Cast, column_type: DataType, dialect: Dialect) -> bool:
    """Tell whether storing the uncast value in the column gives the same result."""
    target = canonical_type(cast.to, dialect)
    name = _CAST_ALIASES.get(target.name, target.name)
    if name == column_type.name and target.is_array == column_type.is_array:
        return True
    return (
        isinstance(_unwrap(cast.this), exp.Literal)
        and target in _LOSSLESS_STRING_CASTS
        and column_type.name in _STRING_TYPES
        and not column_type.is_array
    )


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


def _rewrite(node: exp.Expr, rule: Callable[[exp.Expr], exp.Expr]) -> exp.Expr:
    """Apply ``rule`` until nothing changes; sqlglot skips the inside of replaced nodes."""
    while True:
        rewritten = node.transform(rule)
        if rewritten == node:
            return rewritten
        node = rewritten


_STRING_CAST_TARGETS = frozenset({"text", "varchar", "char", "bpchar"})

# Binding strength of operators, weakest first; anything absent binds like an atom.
_PRECEDENCE: tuple[tuple[type[exp.Expr], ...], ...] = (
    (exp.Or,),
    (exp.And,),
    (exp.Not,),
    (
        exp.EQ,
        exp.NEQ,
        exp.GT,
        exp.GTE,
        exp.LT,
        exp.LTE,
        exp.In,
        exp.Is,
        exp.Like,
        exp.ILike,
        exp.Between,
    ),
    (exp.DPipe,),
    (exp.Add, exp.Sub),
    (exp.Mul, exp.Div, exp.Mod),
    (exp.Neg,),
)
_ATOM = len(_PRECEDENCE)


def _precedence(node: exp.Expr) -> int:
    return next((rank for rank, kinds in enumerate(_PRECEDENCE) if isinstance(node, kinds)), _ATOM)


def _drop_redundant_paren(node: exp.Expr) -> exp.Expr:
    """Remove parentheses that do not change how the expression is evaluated."""
    if not isinstance(node, exp.Paren):
        return node
    child: exp.Expr = node.this
    parent = node.parent
    if not isinstance(parent, exp.Binary | exp.Unary | exp.In | exp.Between):
        return child
    if _precedence(child) > _precedence(parent):
        return child
    # AND and OR are associative, so PostgreSQL prints nested ones without parentheses.
    if type(child) is type(parent) and isinstance(child, exp.And | exp.Or):
        return child
    return node


def _drop_implicit_cast(node: exp.Expr) -> exp.Expr:
    """Remove casts PostgreSQL adds when it stores a condition.

    It casts literals to the type they are compared with, columns to text before text
    operations and array literals to the array type; none of these change the result.
    """
    if not isinstance(node, exp.Cast):
        return node
    inner = _unwrap(node.this)
    if isinstance(inner, exp.Literal | exp.Array | exp.Null | exp.Boolean) or (
        isinstance(inner, exp.Neg) and isinstance(inner.this, exp.Literal)
    ):
        return inner
    target = node.to
    if (
        isinstance(inner, exp.Column)
        and isinstance(target.this, exp.DataType.Type)
        and target.this.value.lower() in _STRING_CAST_TARGETS
    ):
        return inner
    return node


def _any_to_in(node: exp.Expr) -> exp.Expr:
    """Turn ``x = ANY (ARRAY[...])`` back into ``x IN (...)``, and ``<> ALL`` into NOT IN."""
    if not isinstance(node, exp.EQ | exp.NEQ):
        return node
    quantified = node.expression
    if isinstance(node, exp.EQ) and isinstance(quantified, exp.Any):
        array = _unwrap(quantified.this)
    elif (
        isinstance(node, exp.NEQ)
        and isinstance(quantified, exp.Anonymous)
        and str(quantified.this).upper() == "ALL"
        and len(quantified.expressions) == 1
    ):
        array = _unwrap(quantified.expressions[0])
    else:
        return node
    if not isinstance(array, exp.Array):
        return node
    membership = exp.In(this=node.this, expressions=array.expressions)
    return membership if isinstance(node, exp.EQ) else exp.Not(this=membership)
