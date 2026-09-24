"""Mapping of sqlglot data types onto dbdelta's canonical :class:`DataType`."""

from sqlglot import exp
from sqlglot.expressions import DType

from dbdelta.dialects import Dialect, ascii_lower
from dbdelta.model import DataType

_CANONICAL_NAMES: dict[DType, str] = {
    DType.INT: "integer",
    DType.BIGINT: "bigint",
    DType.SMALLINT: "smallint",
    DType.DECIMAL: "numeric",
    DType.FLOAT: "real",
    DType.DOUBLE: "double precision",
    DType.BOOLEAN: "boolean",
}

_BINARY_NAMES = {Dialect.POSTGRESQL: "bytea", Dialect.SQLITE: "blob"}

_SERIAL_TYPES = {
    DType.SMALLSERIAL: DataType("smallint"),
    DType.SERIAL: DataType("integer"),
    DType.BIGSERIAL: DataType("bigint"),
}

# Precision 6 (microseconds) is what these types store when no precision is declared.
_DEFAULT_PRECISION_TYPES = frozenset({"time", "timetz", "timestamp", "timestamptz", "interval"})

# SQL, and PostgreSQL in particular, maps FLOAT(p) with p <= 24 to a 4-byte float.
_REAL_MAX_PRECISION = 24

_DEFAULT_SCHEMAS = {Dialect.POSTGRESQL: "public", Dialect.SQLITE: "main"}


def serial_type(node: exp.DataType, dialect: Dialect) -> DataType | None:
    """Return the integer type behind a PostgreSQL ``serial``-family type, else ``None``."""
    if dialect is Dialect.POSTGRESQL and isinstance(node.this, DType):
        return _SERIAL_TYPES.get(node.this)
    return None


def canonical_type(node: exp.DataType, dialect: Dialect) -> DataType:
    """Convert a parsed type into canonical form.

    Synonyms collapse onto one name, and parameters that restate the dialect default
    are dropped or made explicit, so equal types always produce equal values.
    """
    if node.this == DType.ARRAY:
        # PostgreSQL ignores declared array dimensions, so int[][] is the same type as int[].
        element = canonical_type(node.expressions[0], dialect)
        return DataType(element.name, element.params, is_array=True)
    if node.this == DType.USERDEFINED:
        return DataType(_user_defined_name(node, dialect))
    if not isinstance(node.this, DType):
        # Types with a structured body, such as INTERVAL DAY TO SECOND.
        return DataType(node.this.sql().lower())

    params = _integer_params(node)
    if params is None:
        rendered = ",".join(param.sql() for param in node.expressions)
        return DataType(f"{node.this.value.lower()}({rendered.lower()})")

    if node.this == DType.VARBINARY:
        return DataType(_BINARY_NAMES[dialect])
    if node.this in (DType.FLOAT, DType.DOUBLE):
        if params:
            return DataType("real" if params[0] <= _REAL_MAX_PRECISION else "double precision")
        return DataType(_CANONICAL_NAMES[node.this])

    name = _CANONICAL_NAMES.get(node.this, node.this.value.lower())
    if name in _DEFAULT_PRECISION_TYPES and params == (6,):
        params = ()
    elif name == "numeric" and len(params) == 1:
        params = (params[0], 0)
    elif dialect is Dialect.POSTGRESQL and name in ("char", "bit") and not params:
        params = (1,)
    return DataType(name, params)


def default_schema(dialect: Dialect) -> str:
    """Name of the schema that holds unqualified objects."""
    return _DEFAULT_SCHEMAS[dialect]


def fold_identifier(identifier: exp.Identifier, dialect: Dialect) -> str:
    """Return the name the database stores for an identifier as written in DDL.

    PostgreSQL folds unquoted identifiers to lower case, ASCII letters only. SQLite keeps
    the declared spelling and compares names case-insensitively instead.
    """
    name: str = identifier.this
    if dialect is Dialect.POSTGRESQL and not identifier.quoted:
        return ascii_lower(name)
    return name


def _integer_params(node: exp.DataType) -> tuple[int, ...] | None:
    params: list[int] = []
    for param in node.expressions:
        value = param.this if isinstance(param, exp.DataTypeParam) else param
        if not (isinstance(value, exp.Literal) and not value.is_string and value.is_int):
            return None
        params.append(int(value.this))
    return tuple(params)


def _user_defined_name(node: exp.DataType, dialect: Dialect) -> str:
    kind = node.args.get("kind")
    if isinstance(kind, exp.Identifier):
        return fold_identifier(kind, dialect)
    if isinstance(kind, exp.Dot | exp.Table | exp.Column):
        parts = [fold_identifier(part, dialect) for part in kind.find_all(exp.Identifier)]
        if [ascii_lower(part) for part in parts[:-1]] == [default_schema(dialect)]:
            return parts[-1]
        return ".".join(parts)
    # Free-form SQLite type names such as "UNSIGNED BIG INT"; SQLite compares them
    # case-insensitively.
    return node.sql().lower()
