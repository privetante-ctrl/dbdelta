"""A Markdown report meant for pull request comments (GitHub-flavored Markdown)."""

import re

from dbdelta.cli.analysis import Analysis
from dbdelta.cli.report import Verdict, loader_warnings, migration_sql, summary
from dbdelta.diff import describe
from dbdelta.risk import Finding, Level

_LEVEL_MARKS = {Level.DANGER: "🔴", Level.WARNING: "🟠", Level.INFO: "🔵"}

# Characters that Markdown, or HTML inside it, would interpret within a line or a table cell.
_SPECIAL = re.compile(r"([\\`*_\[\]<|~&])")


def markdown_report(analysis: Analysis, verdict: Verdict | None = None) -> str:
    """The whole report: summary, changes, risks and the migration SQL."""
    lines = [f"### dbdelta: {escape(summary(analysis))}", ""]
    if verdict is not None:
        mark = "✅" if verdict.passed else "❌"
        lines += [f"{mark} **{escape(verdict.explain())}**", ""]
    lines += [
        f"From {code(analysis.source.location)} to {code(analysis.target.location)} "
        f"({analysis.dialect}).",
        "",
    ]
    warnings = loader_warnings(analysis)
    if warnings:
        lines += ["**Not compared:**", ""]
        lines += [f"- {escape(warning)}" for warning in warnings]
        lines.append("")
    if analysis.changes:
        lines += ["| # | Change | Risk |", "|--:|--------|------|"]
        for number, change in enumerate(analysis.changes, 1):
            level = analysis.level_of(change)
            risk = f"{_LEVEL_MARKS[level]} {level}" if level is not None else ""
            lines.append(f"| {number} | {escape(describe(change))} | {risk} |")
        lines.append("")
    if analysis.findings:
        lines += ["#### Risks", ""]
        for finding in analysis.findings:
            lines += _finding(finding)
    if not analysis.script.is_empty:
        lines += [*_details("Migration SQL", fenced(migration_sql(analysis), "sql")), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _finding(finding: Finding) -> list[str]:
    lines = [
        f"- {_LEVEL_MARKS[finding.level]} **{finding.level}** {code(finding.rule)} "
        f"on {escape(finding.subject)}",
        "",
        f"  {escape(finding.message)}",
        "",
        f"  **Safer:** {escape(finding.recommendation)}",
    ]
    if finding.check_sql is not None:
        details = _details("Check before migrating", fenced(finding.check_sql, "sql"))
        lines += ["", *(f"  {line}" if line else "" for line in details)]
    lines.append("")
    return lines


def _details(title: str, content: str) -> list[str]:
    return ["<details>", f"<summary>{title}</summary>", "", *content.splitlines(), "</details>"]


def escape(text: str) -> str:
    """Make ``text`` appear literally in a line of Markdown, table cells included."""
    return _SPECIAL.sub(r"\\\1", " ".join(text.split()))


def code(text: str) -> str:
    """An inline code span holding ``text``, whatever backticks it contains."""
    text = " ".join(text.split())
    ticks = "`" * (_longest_backtick_run(text) + 1)
    # A span that starts or ends with a backtick needs a space to tell it from the fence.
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{padding}{text}{padding}{ticks}"


def fenced(text: str, language: str) -> str:
    """A fenced code block holding ``text``, whatever backtick runs it contains."""
    fence = "`" * max(3, _longest_backtick_run(text) + 1)
    return f"{fence}{language}\n{text.rstrip()}\n{fence}"


def _longest_backtick_run(text: str) -> int:
    return max((len(run) for run in re.findall("`+", text)), default=0)
