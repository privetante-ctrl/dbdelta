"""The registry of risk rules and the function that runs them.

A rule is a function registered under a stable code, the name users see in reports and use
to silence it. Most rules look at one change at a time and are declared with
:func:`change_rule`; rules that need the whole migration use :func:`rule`.
"""

from collections.abc import Callable, Collection, Iterable, Iterator, Sequence
from dataclasses import dataclass

from dbdelta.diff import Change
from dbdelta.risk.context import RiskContext
from dbdelta.risk.findings import Finding

RuleCheck = Callable[[Sequence[Change], RiskContext], Iterable[Finding]]
ChangeCheck = Callable[[Change, RiskContext], Finding | None]


@dataclass(frozen=True, slots=True)
class Rule:
    """A registered risk rule."""

    code: str
    summary: str
    check: RuleCheck


_RULES: dict[str, Rule] = {}


def rule(code: str, summary: str) -> Callable[[RuleCheck], RuleCheck]:
    """Register a rule that inspects the whole list of changes."""

    def register(check: RuleCheck) -> RuleCheck:
        if code in _RULES:
            raise ValueError(f"risk rule {code!r} is registered twice")
        _RULES[code] = Rule(code, summary, check)
        return check

    return register


def change_rule(code: str, summary: str) -> Callable[[ChangeCheck], ChangeCheck]:
    """Register a rule that looks at each change on its own and ignores irrelevant ones."""

    def register(check: ChangeCheck) -> ChangeCheck:
        def check_all(changes: Sequence[Change], context: RiskContext) -> Iterator[Finding]:
            for change in changes:
                finding = check(change, context)
                if finding is not None:
                    yield finding

        rule(code, summary)(check_all)
        return check

    return register


def registered_rules() -> tuple[Rule, ...]:
    """All registered rules, sorted by code."""
    return tuple(_RULES[code] for code in sorted(_RULES))


def assess(
    changes: Sequence[Change], context: RiskContext, *, skip: Collection[str] = ()
) -> tuple[Finding, ...]:
    """Run every registered rule except ``skip``; most dangerous findings first."""
    unknown = sorted(set(skip) - _RULES.keys())
    if unknown:
        raise ValueError(f"unknown risk rule(s): {', '.join(unknown)}")
    findings = [
        finding
        for code, registered in _RULES.items()
        if code not in skip
        for finding in registered.check(changes, context)
    ]
    return tuple(
        sorted(findings, key=lambda found: (-found.level.severity, found.subject, found.rule))
    )
