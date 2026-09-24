import pytest

from dbdelta.cli.analysis import Analysis, LoadedSource
from dbdelta.cli.report import (
    Verdict,
    change_kind,
    change_table,
    loader_warnings,
    migration_sql,
    summary,
)
from dbdelta.dialects import Dialect
from dbdelta.diff import AddColumn, AddEnum, AddTable, Change, DropColumn, SetNotNull
from dbdelta.emit import Block, Script, Statement
from dbdelta.model import Column, DataType, EnumType, Table
from dbdelta.risk import Finding, Level

COLUMN = Column("email", DataType("text"))
ADD = AddColumn("users", COLUMN)
DROP = DropColumn("users", COLUMN)


def _finding(level: Level, *changes: Change) -> Finding:
    return Finding("rule", level, "users.email", "message", "recommendation", changes)


def _analysis(
    changes: tuple[Change, ...] = (),
    findings: tuple[Finding, ...] = (),
    warnings: tuple[str, ...] = (),
) -> Analysis:
    script = Script((Block((Statement("SELECT 1"),), transactional=True),)) if changes else Script()
    return Analysis(
        Dialect.POSTGRESQL,
        LoadedSource("a.sql", warnings),
        LoadedSource("postgresql://app:***@db/app", ()),
        changes,
        findings,
        script,
    )


@pytest.mark.parametrize(
    ("analysis", "text"),
    [
        (_analysis(), "No changes: the schemas are identical."),
        (_analysis((ADD,)), "1 change, no risks found."),
        (
            _analysis((ADD, DROP), (_finding(Level.DANGER, DROP), _finding(Level.INFO, ADD))),
            "2 changes, 2 risks: 1 danger, 1 info.",
        ),
        (_analysis((DROP,), (_finding(Level.WARNING, DROP),)), "1 change, 1 risk: 1 warning."),
    ],
)
def test_summary(analysis: Analysis, text: str) -> None:
    assert summary(analysis) == text


def test_a_change_takes_the_level_of_its_most_severe_finding() -> None:
    analysis = _analysis((ADD, DROP), (_finding(Level.WARNING, DROP), _finding(Level.DANGER, DROP)))

    assert analysis.level_of(DROP) is Level.DANGER
    assert analysis.level_of(ADD) is None


def test_dangerous_changes_fail_the_check_unless_allowed() -> None:
    analysis = _analysis((DROP, ADD), (_finding(Level.DANGER, DROP), _finding(Level.INFO, ADD)))

    failed = Verdict.of(analysis, allow_destructive=False)
    allowed = Verdict.of(analysis, allow_destructive=True)

    assert not failed.passed
    assert failed.explain().startswith("Check failed: 1 dangerous change. Review them")
    assert allowed.passed
    assert allowed.explain() == "Check passed: 1 dangerous change allowed by --allow-destructive."


def test_warnings_do_not_fail_the_check() -> None:
    verdict = Verdict.of(
        _analysis((ADD,), (_finding(Level.WARNING, ADD),)), allow_destructive=False
    )

    assert verdict.passed
    assert verdict.explain() == "Check passed: no dangerous changes."


def test_loader_warnings_name_their_source() -> None:
    analysis = _analysis(warnings=("skipped view 'v': it is not supported",))

    assert loader_warnings(analysis) == ["a.sql: skipped view 'v': it is not supported"]


def test_migration_sql_starts_with_a_header() -> None:
    analysis = _analysis((ADD,), (_finding(Level.INFO, ADD),), ("skipped view 'v'",))

    sql = migration_sql(analysis)

    assert sql.startswith("-- Migration from a.sql to postgresql://app:***@db/app (postgresql)")
    assert "-- 1 change, 1 risk: 1 info.\n" in sql
    assert "-- Not compared: a.sql: skipped view 'v'\n" in sql
    assert sql.endswith("BEGIN;\n\nSELECT 1;\n\nCOMMIT;\n")


def test_migration_sql_without_changes_is_only_a_comment() -> None:
    sql = migration_sql(_analysis())

    assert sql.endswith("-- No changes: the schemas are identical.\n")
    assert all(line.startswith("--") for line in sql.splitlines())


@pytest.mark.parametrize(
    ("change", "kind", "table"),
    [
        (ADD, "add_column", "users"),
        (SetNotNull("users", "email"), "set_not_null", "users"),
        (AddTable(Table("users", (COLUMN,))), "add_table", "users"),
        (AddEnum(EnumType("mood", ("ok",))), "add_enum", None),
    ],
)
def test_changes_have_a_kind_and_a_table(change: Change, kind: str, table: str | None) -> None:
    assert change_kind(change) == kind
    assert change_table(change) == table
