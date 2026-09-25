"""The machine-readable report."""

import json
from typing import Any

from dbdelta import __version__
from dbdelta.cli.analysis import Analysis, LoadedSource
from dbdelta.cli.report import LEVELS, Verdict, change_kind, change_table, migration_sql
from dbdelta.diff import describe


def json_report(analysis: Analysis, verdict: Verdict | None = None) -> str:
    """The analysis as JSON; findings refer to changes by their index in ``changes``."""
    index = {change: number for number, change in enumerate(analysis.changes)}
    document: dict[str, Any] = {
        "dbdelta": __version__,
        "dialect": analysis.dialect.value,
        "direction": "down" if analysis.down else "up",
        "source": _source(analysis.source),
        "target": _source(analysis.target),
        "summary": {
            "changes": len(analysis.changes),
            **{level.value: analysis.count(level) for level in LEVELS},
            "irreversible": len(analysis.irreversible),
        },
        "changes": [
            {
                "kind": change_kind(change),
                "table": change_table(change),
                "description": describe(change),
                "risk": analysis.level_of(change),
                "irreversible": analysis.irreversible_reason(change),
            }
            for change in analysis.changes
        ],
        "findings": [
            {
                "rule": finding.rule,
                "level": finding.level.value,
                "subject": finding.subject,
                "message": finding.message,
                "recommendation": finding.recommendation,
                "check_sql": finding.check_sql,
                "changes": [index[change] for change in finding.changes],
            }
            for finding in analysis.findings
        ],
        "sql": migration_sql(analysis),
    }
    if verdict is not None:
        document["check"] = {
            "passed": verdict.passed,
            "allow_destructive": verdict.allow_destructive,
            "dangers": len(verdict.dangers),
        }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _source(source: LoadedSource) -> dict[str, Any]:
    return {"location": source.location, "warnings": list(source.warnings)}
