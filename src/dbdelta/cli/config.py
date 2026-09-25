"""Settings from ``dbdelta.toml``, which command-line options override."""

import difflib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import TypeVar

from dbdelta.dialects import Dialect
from dbdelta.risk import DEFAULT_LARGE_TABLE_ROWS

CONFIG_FILE = "dbdelta.toml"

_T = TypeVar("_T")


class ConfigError(Exception):
    """The configuration file cannot be read or holds an invalid setting."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything that shapes a comparison besides the two sources.

    ``dialect`` is ``None`` when neither a URL nor the user names one; the CLI then falls
    back to PostgreSQL for schema files.
    """

    dialect: Dialect | None = None
    schema: str | None = None
    ignore_tables: tuple[str, ...] = ()
    ignore_rules: tuple[str, ...] = ()
    strict_column_order: bool = False
    detect_renames: bool = False
    concurrent_indexes: bool = False
    allow_destructive: bool = False
    large_table_rows: int = DEFAULT_LARGE_TABLE_ROWS

    def override(
        self,
        *,
        dialect: Dialect | None = None,
        schema: str | None = None,
        ignore_tables: tuple[str, ...] = (),
        ignore_rules: tuple[str, ...] = (),
        strict_column_order: bool | None = None,
        detect_renames: bool | None = None,
        concurrent_indexes: bool | None = None,
        allow_destructive: bool | None = None,
        large_table_rows: int | None = None,
    ) -> "Settings":
        """Apply command-line options: given values replace settings, patterns add to them."""
        return replace(
            self,
            dialect=dialect or self.dialect,
            schema=schema or self.schema,
            ignore_tables=self.ignore_tables + ignore_tables,
            ignore_rules=self.ignore_rules + ignore_rules,
            strict_column_order=_pick(strict_column_order, self.strict_column_order),
            detect_renames=_pick(detect_renames, self.detect_renames),
            concurrent_indexes=_pick(concurrent_indexes, self.concurrent_indexes),
            allow_destructive=_pick(allow_destructive, self.allow_destructive),
            large_table_rows=_pick(large_table_rows, self.large_table_rows),
        )


def _pick(given: _T | None, current: _T) -> _T:
    return current if given is None else given


def find_config(explicit: Path | None, directory: Path) -> Path | None:
    """The configuration file to use: the one given, else ``dbdelta.toml`` in ``directory``."""
    if explicit is not None:
        return explicit
    candidate = directory / CONFIG_FILE
    return candidate if candidate.is_file() else None


def read_config(path: Path) -> Settings:
    """Read and validate a configuration file."""
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from error
    try:
        return parse_config(data)
    except ConfigError as error:
        raise ConfigError(f"{path}: {error}") from error


_KEYS = {field.name.replace("_", "-") for field in fields(Settings)}


def parse_config(data: Mapping[str, object]) -> Settings:
    """Build settings from the parsed TOML document, rejecting unknown or mistyped keys.

    Keys are spelled like the command-line options, ``ignore-tables`` and so on. Unknown
    keys are errors rather than being ignored, so that a typo does not silently change
    what the migration contains.
    """
    for key in data:
        if key not in _KEYS:
            close = difflib.get_close_matches(key, _KEYS, n=1)
            hint = f"; did you mean {close[0]!r}?" if close else ""
            raise ConfigError(f"unknown setting {key!r}{hint}")
    defaults = Settings()
    return Settings(
        dialect=_dialect(data),
        schema=_schema(data),
        ignore_tables=_strings(data, "ignore-tables"),
        ignore_rules=_strings(data, "ignore-rules"),
        strict_column_order=_flag(data, "strict-column-order", defaults.strict_column_order),
        detect_renames=_flag(data, "detect-renames", defaults.detect_renames),
        concurrent_indexes=_flag(data, "concurrent-indexes", defaults.concurrent_indexes),
        allow_destructive=_flag(data, "allow-destructive", defaults.allow_destructive),
        large_table_rows=_row_count(data, "large-table-rows", defaults.large_table_rows),
    )


def _dialect(data: Mapping[str, object]) -> Dialect | None:
    value = data.get("dialect")
    if value is None:
        return None
    if not isinstance(value, str) or value not in set(Dialect):
        choices = ", ".join(dialect.value for dialect in Dialect)
        raise ConfigError(f"dialect must be one of: {choices}")
    return Dialect(value)


def _schema(data: Mapping[str, object]) -> str | None:
    value = data.get("schema")
    if value is not None and (not isinstance(value, str) or not value):
        raise ConfigError("schema must be a schema name")
    return value


def _strings(data: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a list of strings")
    return tuple(value)


def _flag(data: Mapping[str, object], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false")
    return value


def _row_count(data: Mapping[str, object], key: str, default: int) -> int:
    value = data.get(key, default)
    # bool is a subclass of int, and `true` is certainly not a row count.
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"{key} must be a positive integer")
    return value
