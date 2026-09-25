"""The human-readable report, rendered with Rich.

User data (names, conditions, file paths) only ever enters Rich as :class:`Text`, never as
markup, so a table called ``[red]`` is printed as it is.
"""

from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from dbdelta.cli.analysis import Analysis
from dbdelta.cli.report import Verdict, loader_warnings, risk_label, summary
from dbdelta.diff import describe
from dbdelta.risk import Finding, Level

LEVEL_STYLES = {Level.DANGER: "bold red", Level.WARNING: "yellow", Level.INFO: "blue"}


def text_report(analysis: Analysis, verdict: Verdict | None = None) -> RenderableType:
    """The report of ``dbdelta diff`` and ``dbdelta check``."""
    parts: list[RenderableType] = [
        Text.assemble(
            ("Down: " if analysis.down else "", "bold"),
            (analysis.start.location, "cyan"),
            " -> ",
            (analysis.end.location, "cyan"),
            f" ({analysis.dialect})",
        )
    ]
    warnings = loader_warnings(analysis)
    if warnings:
        parts.append(_section("Not compared"))
        parts += [_indent(Text(warning, style="yellow")) for warning in warnings]
    if analysis.changes:
        parts += [_section("Changes"), _changes(analysis)]
    if analysis.irreversible:
        parts.append(_section("Irreversible"))
        for step in analysis.irreversible:
            heading = Text.assemble(("IRREVERSIBLE", "bold magenta"), "  ", describe(step.change))
            parts += [Text(), heading, _indent(Text(step.reason))]
    if analysis.findings:
        parts.append(_section("Risks"))
        parts += [_finding(finding) for finding in analysis.findings]
    parts += [Text(), Text(summary(analysis), style="bold")]
    if verdict is not None:
        parts.append(_verdict(verdict))
    return Group(*parts)


def _section(title: str) -> Text:
    return Text(f"\n{title}", style="bold underline")


def _changes(analysis: Analysis) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Change", overflow="fold")
    table.add_column("Risk")
    for number, change in enumerate(analysis.changes, 1):
        level = analysis.level_of(change)
        risk = Text(risk_label(analysis, change))
        if level is not None:
            risk.stylize(LEVEL_STYLES[level], 0, len(level))
        table.add_row(str(number), Text(describe(change)), risk)
    return table


def _finding(finding: Finding) -> RenderableType:
    heading = Text.assemble(
        (finding.level.upper(), LEVEL_STYLES[finding.level]),
        "  ",
        (finding.rule, "bold"),
        "  ",
        finding.subject,
    )
    body: list[RenderableType] = [
        Text(finding.message),
        Text.assemble(("Safer: ", "green"), finding.recommendation),
    ]
    if finding.check_sql is not None:
        body += [Text("Check before migrating:", style="green"), _indent(Text(finding.check_sql))]
    return Group(Text(), heading, _indent(Group(*body)))


def _verdict(verdict: Verdict) -> Text:
    if not verdict.passed:
        style = "bold red"
    elif verdict.dangers:
        style = "bold yellow"
    else:
        style = "bold green"
    return Text(verdict.explain(), style=style)


def _indent(renderable: RenderableType) -> Padding:
    return Padding(renderable, (0, 0, 0, 2))
