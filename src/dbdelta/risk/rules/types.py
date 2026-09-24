"""Column type changes that can lose data or rewrite the table."""

from dbdelta.dialects.postgresql import needs_explicit_cast, rewrites_table
from dbdelta.dialects.quoting import quote_identifier
from dbdelta.diff import AlterColumnType, Change
from dbdelta.model import DataType
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding, Level
from dbdelta.risk.registry import change_rule
from dbdelta.risk.rules._helpers import LOCK_BLOCKS_ALL, column, is_postgresql, lock_level

_INTEGERS = {"smallint": 1, "integer": 2, "bigint": 3}
_INTEGER_RANGES = {
    "smallint": (-32768, 32767),
    "integer": (-2147483648, 2147483647),
    "bigint": (-9223372036854775808, 9223372036854775807),
}
_INTEGER_DIGITS = {"smallint": 5, "integer": 10, "bigint": 19}
_FLOATS = {"real": 1, "double precision": 2}
_STRINGS = frozenset({"text", "varchar", "char"})
_TIMES = frozenset({"time", "timetz", "timestamp", "timestamptz", "interval"})
_DEFAULT_TIME_PRECISION = 6


def is_narrowing(old: DataType, new: DataType) -> bool:
    """Tell whether some values of ``old`` do not fit into ``new`` without loss."""
    if old.is_array != new.is_array:
        return False
    if old.name in _INTEGERS:
        if new.name in _INTEGERS:
            return _INTEGERS[new.name] < _INTEGERS[old.name]
        if new.name == "numeric" and new.params:
            precision, scale = new.params
            return precision - scale < _INTEGER_DIGITS[old.name]
        return False
    if old.name in _FLOATS:
        return new.name in _INTEGERS or (
            new.name in _FLOATS and _FLOATS[new.name] < _FLOATS[old.name]
        )
    if old.name == "numeric":
        return _narrows_numeric(old, new)
    if old.name in _STRINGS and new.name in _STRINGS and new.params:
        return not old.params or new.params[0] < old.params[0]
    if old.name in _TIMES and old.name == new.name:
        return _precision(new) < _precision(old)
    return False


@change_rule("narrowing-type", "A narrower column type cannot hold every existing value.")
def narrowing_type(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AlterColumnType) or not is_narrowing(change.old, change.new):
        return None
    subject = f"{change.table}.{change.column}"
    if not is_postgresql(context):
        return Finding(
            "narrowing-type",
            Level.INFO,
            subject,
            f"{subject} changes from {change.old} to the narrower {change.new}. SQLite does "
            "not enforce declared lengths or ranges, so stored values stay as they are.",
            "Make sure the application no longer writes values that do not fit.",
            (change,),
            check_sql=_fit_check(change),
        )
    return Finding(
        "narrowing-type",
        Level.DANGER,
        subject,
        f"{subject} changes from {change.old} to the narrower {change.new}. "
        f"{_consequence(change.new)}",
        "Check the data with the query below and clean up values that do not fit, or keep "
        "the wider type.",
        (change,),
        check_sql=_fit_check(change),
    )


@change_rule("type-rewrite", "Some type changes rewrite the whole table under a lock.")
def type_rewrite(change: Change, context: RiskContext) -> Finding | None:
    if not isinstance(change, AlterColumnType) or not is_postgresql(context):
        return None
    if not rewrites_table(change.old, change.new):
        return None
    subject = f"{change.table}.{change.column}"
    converted = ""
    if needs_explicit_cast(change.old, change.new):
        converted = (
            f"There is no automatic conversion from {change.old} to {change.new}, so values "
            "are converted with USING and any value that does not convert makes the "
            "migration fail. "
        )
    return Finding(
        "type-rewrite",
        lock_level(context, change.table),
        subject,
        f"{converted}Changing {subject} from {change.old} to {change.new} makes PostgreSQL "
        f"rewrite the whole table and its indexes while holding {LOCK_BLOCKS_ALL}.",
        "On a large table, add a new column of the new type, backfill it in batches, switch "
        "the application over and drop the old column; otherwise run the migration in a "
        "maintenance window.",
        (change,),
    )


def _narrows_numeric(old: DataType, new: DataType) -> bool:
    if new.name in _INTEGERS:
        return not old.params or old.params[1] > 0 or old.params[0] > _INTEGER_DIGITS[new.name] - 1
    if new.name in _FLOATS:
        return True
    if new.name != "numeric" or not new.params:
        return False
    if not old.params:
        return True
    old_precision, old_scale = old.params
    new_precision, new_scale = new.params
    return new_scale < old_scale or new_precision - new_scale < old_precision - old_scale


def _consequence(new: DataType) -> str:
    if new.name in _STRINGS:
        return f"Values longer than {new.params[0]} characters make the migration fail."
    if new.name in _INTEGERS:
        return f"Values outside the range of {new} make the migration fail."
    if new.name in _TIMES:
        return "Fractional seconds beyond the new precision are rounded away."
    return (
        "Values that do not fit make the migration fail, and digits beyond the new precision "
        "are rounded away."
    )


def _precision(data_type: DataType) -> int:
    return data_type.params[0] if data_type.params else _DEFAULT_TIME_PRECISION


def _fit_check(change: AlterColumnType) -> str | None:
    table, new = quote_identifier(change.table), change.new
    reference = column(change.table, change.column)
    if new.name in _STRINGS and new.params:
        condition = f"length({reference}) > {new.params[0]}"
    elif new.name in _INTEGERS:
        low, high = _INTEGER_RANGES[new.name]
        condition = f"{reference} NOT BETWEEN {low} AND {high}"
    elif new.name == "numeric" and new.params:
        precision, scale = new.params
        condition = f"abs({reference}) >= 1e{precision - scale}"
    else:
        return None
    return f"SELECT count(*) FROM {table} WHERE {condition}"
