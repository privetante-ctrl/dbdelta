"""Typer application that wires the dbdelta commands together."""

from typing import Annotated

import typer

from dbdelta import __version__

app = typer.Typer(
    name="dbdelta",
    help="Compare two database schemas and generate a safe migration script.",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"dbdelta {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Compare two database schemas and generate a safe migration script."""
