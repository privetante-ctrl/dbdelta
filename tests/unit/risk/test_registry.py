from collections.abc import Iterator, Sequence

import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import Change, DropColumn, DropTable
from dbdelta.model import Column, DataType, Schema, Table
from dbdelta.risk import Finding, Level, RiskContext, assess, registered_rules, registry, rule

TABLE = Table("t", (Column("a", DataType("integer")), Column("b", DataType("integer"))))
CONTEXT = RiskContext(Dialect.POSTGRESQL, Schema((TABLE,)), Schema())


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_RULES", dict(registry._RULES))


def test_rules_have_unique_codes_and_summaries() -> None:
    rules = registered_rules()

    assert [found.code for found in rules] == sorted({found.code for found in rules})
    assert all(found.summary.endswith(".") for found in rules)


def test_registering_a_code_twice_is_an_error() -> None:
    with pytest.raises(ValueError, match="'drop-table' is registered twice"):
        rule("drop-table", "Again.")(lambda _changes, _context: ())


def test_findings_come_most_dangerous_first() -> None:
    @rule("test-info", "Always reports.")
    def always(_changes: Sequence[Change], _context: RiskContext) -> Iterator[Finding]:
        yield Finding("test-info", Level.INFO, "a", "message", "recommendation", ())

    changes = (DropTable(TABLE), DropColumn("t", TABLE.columns[1]))

    levels = [finding.level for finding in assess(changes, CONTEXT)]

    assert levels == [Level.DANGER, Level.DANGER, Level.INFO]


def test_skipped_rules_do_not_run() -> None:
    findings = assess((DropTable(TABLE),), CONTEXT, skip={"drop-table"})

    assert findings == ()


def test_skipping_an_unknown_rule_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown risk rule"):
        assess((), CONTEXT, skip={"no-such-rule"})


def test_levels_are_ordered_by_severity() -> None:
    assert Level.INFO.severity < Level.WARNING.severity < Level.DANGER.severity
