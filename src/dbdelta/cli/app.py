"""Typer application that wires the dbdelta commands together.

Exit codes: 0 on success, 1 when ``dbdelta check`` finds dangerous changes that are not
allowed, 2 when the command line, the configuration or a source is invalid.
"""

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console, RenderableType

from dbdelta import __version__
from dbdelta.cli.analysis import Analysis, analyze
from dbdelta.cli.config import ConfigError, Settings, find_config, read_config
from dbdelta.cli.json_report import json_report
from dbdelta.cli.markdown import markdown_report
from dbdelta.cli.report import OutputFormat, Verdict, loader_warnings, migration_sql, summary
from dbdelta.cli.text import text_report
from dbdelta.dialects import Dialect
from dbdelta.loaders import LoadError
from dbdelta.risk import DEFAULT_LARGE_TABLE_ROWS, registered_rules

EXIT_CHECK_FAILED = 1
EXIT_USAGE = 2

app = typer.Typer(
    name="dbdelta",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"dbdelta {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[  # noqa: ARG001 - handled by its eager callback
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Compare two database schemas and generate a safe migration script.

    SOURCE is the current schema and TARGET the desired one. Each is a .sql file or a
    database URL such as postgresql://user@host/db or sqlite:///app.db. Settings are also
    read from dbdelta.toml in the current directory.
    """
    # dbdelta reports statements sqlglot cannot parse on its own, with more context.
    logging.getLogger("sqlglot").setLevel(logging.ERROR)


Source = Annotated[
    str, typer.Argument(metavar="SOURCE", help="Current schema: a .sql file or a database URL.")
]
Target = Annotated[
    str, typer.Argument(metavar="TARGET", help="Desired schema: a .sql file or a database URL.")
]
DialectOption = Annotated[
    Dialect | None,
    typer.Option(
        "--dialect",
        "-d",
        case_sensitive=False,
        help="Dialect of .sql files; URLs name their own.",
        show_default="postgresql",
    ),
]
SchemaOption = Annotated[
    str | None,
    typer.Option(help="PostgreSQL schema to compare on both sides.", show_default="public"),
]
FormatOption = Annotated[
    OutputFormat | None,
    typer.Option("--format", "-f", case_sensitive=False, help="Output format.", show_default=False),
]
OutputOption = Annotated[
    Path | None,
    typer.Option("--output", "-o", dir_okay=False, help="Write the output to this file."),
]
IgnoreTableOption = Annotated[
    list[str] | None,
    typer.Option(
        "--ignore-table",
        metavar="PATTERN",
        help="Leave out tables matching this shell-style pattern, such as 'django_*'. Repeatable.",
    ),
]
IgnoreRuleOption = Annotated[
    list[str] | None,
    typer.Option("--ignore-rule", metavar="RULE", help="Do not run this risk rule. Repeatable."),
]
StrictColumnOrderOption = Annotated[
    bool | None,
    typer.Option(
        "--strict-column-order/--no-strict-column-order",
        help="Treat a different order of table columns as a change.",
        show_default=False,
    ),
]
ConcurrentIndexesOption = Annotated[
    bool | None,
    typer.Option(
        "--concurrent-indexes/--no-concurrent-indexes",
        help="Build and drop PostgreSQL indexes CONCURRENTLY, outside the transaction.",
        show_default=False,
    ),
]
LargeTableRowsOption = Annotated[
    int | None,
    typer.Option(
        min=1,
        metavar="ROWS",
        help="Row count from which a table counts as large for lock warnings.",
        show_default=str(DEFAULT_LARGE_TABLE_ROWS),
    ),
]
ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        dir_okay=False,
        help="Configuration file.",
        show_default="dbdelta.toml, if present",
    ),
]
AllowDestructiveOption = Annotated[
    bool | None,
    typer.Option(
        "--allow-destructive/--no-allow-destructive",
        help="Pass the check even if changes are dangerous.",
        show_default=False,
    ),
]


@dataclass(frozen=True, slots=True)
class _Options:
    """The command-line options that all commands share."""

    dialect: Dialect | None
    schema: str | None
    output_format: OutputFormat | None
    output: Path | None
    ignore_tables: list[str] | None
    ignore_rules: list[str] | None
    strict_column_order: bool | None
    concurrent_indexes: bool | None
    large_table_rows: int | None
    config: Path | None


@app.command()
def diff(
    source: Source,
    target: Target,
    *,
    dialect: DialectOption = None,
    schema: SchemaOption = None,
    output_format: FormatOption = None,
    output: OutputOption = None,
    ignore_table: IgnoreTableOption = None,
    ignore_rule: IgnoreRuleOption = None,
    strict_column_order: StrictColumnOrderOption = None,
    concurrent_indexes: ConcurrentIndexesOption = None,
    large_table_rows: LargeTableRowsOption = None,
    config: ConfigOption = None,
) -> None:
    """Show what differs between SOURCE and TARGET and how risky migrating is.

    The default output is a report; --format sql prints the migration instead.
    """
    options = _Options(
        dialect,
        schema,
        output_format,
        output,
        ignore_table,
        ignore_rule,
        strict_column_order,
        concurrent_indexes,
        large_table_rows,
        config,
    )
    _run(source, target, options, default_format=OutputFormat.TEXT)


@app.command()
def plan(
    source: Source,
    target: Target,
    *,
    dialect: DialectOption = None,
    schema: SchemaOption = None,
    output_format: FormatOption = None,
    output: OutputOption = None,
    ignore_table: IgnoreTableOption = None,
    ignore_rule: IgnoreRuleOption = None,
    strict_column_order: StrictColumnOrderOption = None,
    concurrent_indexes: ConcurrentIndexesOption = None,
    large_table_rows: LargeTableRowsOption = None,
    config: ConfigOption = None,
) -> None:
    """Print the SQL that migrates SOURCE to TARGET.

    Risks are written as comments above the statements they concern.
    """
    options = _Options(
        dialect,
        schema,
        output_format,
        output,
        ignore_table,
        ignore_rule,
        strict_column_order,
        concurrent_indexes,
        large_table_rows,
        config,
    )
    _run(source, target, options, default_format=OutputFormat.SQL)


@app.command()
def check(
    source: Source,
    target: Target,
    *,
    dialect: DialectOption = None,
    schema: SchemaOption = None,
    output_format: FormatOption = None,
    output: OutputOption = None,
    ignore_table: IgnoreTableOption = None,
    ignore_rule: IgnoreRuleOption = None,
    strict_column_order: StrictColumnOrderOption = None,
    concurrent_indexes: ConcurrentIndexesOption = None,
    large_table_rows: LargeTableRowsOption = None,
    config: ConfigOption = None,
    allow_destructive: AllowDestructiveOption = None,
) -> None:
    """Fail with exit code 1 if migrating SOURCE to TARGET is dangerous; for CI.

    Dangerous changes, such as dropping a table or narrowing a type, fail the check unless
    --allow-destructive is given.
    """
    options = _Options(
        dialect,
        schema,
        output_format,
        output,
        ignore_table,
        ignore_rule,
        strict_column_order,
        concurrent_indexes,
        large_table_rows,
        config,
    )
    _run(
        source,
        target,
        options,
        default_format=OutputFormat.TEXT,
        check=True,
        allow_destructive=allow_destructive,
    )


def _run(
    source: str,
    target: str,
    options: _Options,
    *,
    default_format: OutputFormat,
    check: bool = False,
    allow_destructive: bool | None = None,
) -> None:
    settings = _settings(options, allow_destructive)
    try:
        analysis = analyze(source, target, settings)
    except LoadError as error:
        _fail(str(error))
    verdict = Verdict.of(analysis, allow_destructive=settings.allow_destructive) if check else None
    output_format = options.output_format or default_format
    _write(analysis, verdict, output_format, options.output)
    if verdict is not None and not verdict.passed:
        raise typer.Exit(EXIT_CHECK_FAILED)


def _settings(options: _Options, allow_destructive: bool | None) -> Settings:
    path = find_config(options.config, Path.cwd())
    try:
        configured = read_config(path) if path is not None else Settings()
    except ConfigError as error:
        _fail(str(error))
    settings = configured.override(
        dialect=options.dialect,
        schema=options.schema,
        ignore_tables=tuple(options.ignore_tables or ()),
        ignore_rules=tuple(options.ignore_rules or ()),
        strict_column_order=options.strict_column_order,
        concurrent_indexes=options.concurrent_indexes,
        allow_destructive=allow_destructive,
        large_table_rows=options.large_table_rows,
    )
    known = {rule.code for rule in registered_rules()}
    unknown = sorted(set(settings.ignore_rules) - known)
    if unknown:
        _fail(
            f"unknown risk rule(s): {', '.join(unknown)}; the rules are: {', '.join(sorted(known))}"
        )
    return settings


def _write(
    analysis: Analysis, verdict: Verdict | None, output_format: OutputFormat, output: Path | None
) -> None:
    """Print the output, or write it to ``output``, and report status on stderr.

    Status that the output does not show on the terminal (loader warnings, the check
    verdict, where the output went) goes to stderr, which keeps stdout fit for a pipe.
    """
    stdout = Console()
    if output is None and output_format is OutputFormat.TEXT:
        if stdout.is_terminal:
            stdout.print(text_report(analysis, verdict))
        else:
            typer.echo(_plain_text(text_report(analysis, verdict), stdout.width), nl=False)
        return
    content = _render(analysis, verdict, output_format)
    if output is None:
        typer.echo(content, nl=False)
    else:
        try:
            output.write_text(content, encoding="utf-8")
        except OSError as error:
            _fail(f"cannot write {output}: {error.strerror}")
    for warning in loader_warnings(analysis):
        _status(f"warning: {warning}", "yellow")
    if output is not None:
        what = "the migration" if output_format is OutputFormat.SQL else "the report"
        _status(f"Wrote {what} to {output}. {summary(analysis)}")
    if verdict is not None:
        _status(verdict.explain(), "bold green" if verdict.passed else "bold red")


def _render(analysis: Analysis, verdict: Verdict | None, output_format: OutputFormat) -> str:
    match output_format:
        case OutputFormat.SQL:
            return migration_sql(analysis)
        case OutputFormat.JSON:
            return json_report(analysis, verdict)
        case OutputFormat.MARKDOWN:
            return markdown_report(analysis, verdict)
        case OutputFormat.TEXT:
            return _plain_text(text_report(analysis, verdict), _FILE_WIDTH)


_FILE_WIDTH = 100


def _plain_text(renderable: RenderableType, width: int) -> str:
    """Render without colors or the padding Rich adds to the end of lines."""
    buffer = io.StringIO()
    # An explicit color system of None also overrides FORCE_COLOR, which CI services set.
    Console(file=buffer, width=width, color_system=None).print(renderable)
    return "".join(line.rstrip() + "\n" for line in buffer.getvalue().splitlines())


def _status(message: str, style: str = "") -> None:
    """Print a line to stderr; soft wrapping keeps paths and URLs in one piece."""
    Console(stderr=True).print(message, style=style, markup=False, highlight=False, soft_wrap=True)


def _fail(message: str) -> NoReturn:
    _status(f"error: {message}", "bold red")
    raise typer.Exit(EXIT_USAGE)
