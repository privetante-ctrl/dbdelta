import runpy
import sys

import pytest
from typer.testing import CliRunner

from dbdelta import __version__
from dbdelta.cli.app import app

runner = CliRunner()


def test_version_option_prints_version_and_exits() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == f"dbdelta {__version__}\n"


def test_running_without_arguments_shows_help() -> None:
    result = runner.invoke(app, [])

    assert "Usage: dbdelta" in result.output


def test_package_is_runnable_as_module(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["dbdelta", "--version"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("dbdelta", run_name="__main__")

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"dbdelta {__version__}\n"
