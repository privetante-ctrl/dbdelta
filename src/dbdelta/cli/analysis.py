"""Run the whole pipeline for two sources: load, diff, assess, plan and emit."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase

from dbdelta.cli.config import Settings
from dbdelta.dialects import Dialect, name_key
from dbdelta.diff import Change, diff_schemas
from dbdelta.emit import EmitOptions, Script, emit_migration
from dbdelta.loaders import (
    LoadError,
    LoadResult,
    describe_source,
    dialect_from_url,
    is_url,
    load_source,
)
from dbdelta.model import Schema
from dbdelta.plan import plan_migration
from dbdelta.risk import Finding, Level, RiskContext, assess

DEFAULT_DIALECT = Dialect.POSTGRESQL


@dataclass(frozen=True, slots=True)
class LoadedSource:
    """One side of the comparison as it was loaded."""

    location: str
    """Where the schema came from: a path, or a URL without its password."""

    warnings: tuple[str, ...]
    """What the loader skipped or could not represent."""


@dataclass(frozen=True, slots=True)
class Analysis:
    """Everything dbdelta found out about a migration, ready to be reported."""

    dialect: Dialect
    source: LoadedSource
    target: LoadedSource
    changes: tuple[Change, ...]
    findings: tuple[Finding, ...]
    script: Script

    def count(self, level: Level) -> int:
        return sum(1 for finding in self.findings if finding.level is level)

    def level_of(self, change: Change) -> Level | None:
        """The most severe level of the findings about ``change``."""
        levels = [finding.level for finding in self.findings if change in finding.changes]
        return max(levels, key=lambda level: level.severity, default=None)


def analyze(source: str, target: str, settings: Settings) -> Analysis:
    """Compare the schema at ``source`` with the desired one at ``target``.

    Raises :class:`~dbdelta.loaders.LoadError` when a source cannot be read and
    :class:`ValueError` for a risk rule name that does not exist.
    """
    dialect = resolve_dialect((source, target), settings.dialect)
    loaded_source = load_source(source, dialect, settings.schema)
    loaded_target = load_source(target, dialect, settings.schema)
    old = without_tables(loaded_source.schema, settings.ignore_tables, dialect)
    new = without_tables(loaded_target.schema, settings.ignore_tables, dialect)

    changes = diff_schemas(old, new, dialect, strict_column_order=settings.strict_column_order)
    context = RiskContext(
        dialect,
        old,
        new,
        row_estimates=loaded_source.row_estimates,
        large_table_rows=settings.large_table_rows,
        concurrent_indexes=settings.concurrent_indexes,
    )
    findings = assess(changes, context, skip=settings.ignore_rules)
    plan = plan_migration(changes, old, new, dialect)
    script = emit_migration(
        plan, EmitOptions(concurrent_indexes=settings.concurrent_indexes), findings
    )
    return Analysis(
        dialect=dialect,
        source=_loaded(source, loaded_source),
        target=_loaded(target, loaded_target),
        changes=changes,
        findings=findings,
        script=script,
    )


def resolve_dialect(sources: Sequence[str], configured: Dialect | None) -> Dialect:
    """The dialect of the comparison: the one of the URLs, else the configured one.

    Both sides must be the same kind of database, because a migration is written in one
    dialect.
    """
    from_urls = {dialect_from_url(source) for source in sources if is_url(source)}
    if len(from_urls) > 1:
        names = " and ".join(sorted(from_urls))
        raise LoadError(f"cannot compare {names} databases; both sides must use one dialect")
    if from_urls:
        (dialect,) = from_urls
        if configured is not None and configured is not dialect:
            raise LoadError(f"--dialect {configured} does not match the {dialect} database")
        return dialect
    return configured or DEFAULT_DIALECT


def without_tables(schema: Schema, patterns: Collection[str], dialect: Dialect) -> Schema:
    """Leave out the tables whose names match any of the shell-style ``patterns``.

    Names match as the database compares them: case-insensitively in SQLite.
    """
    if not patterns:
        return schema
    keys = [name_key(pattern, dialect) for pattern in patterns]
    kept = tuple(
        table
        for table in schema.tables
        if not any(fnmatchcase(name_key(table.name, dialect), key) for key in keys)
    )
    return replace(schema, tables=kept)


def _loaded(source: str, result: LoadResult) -> LoadedSource:
    return LoadedSource(describe_source(source), result.warnings)
