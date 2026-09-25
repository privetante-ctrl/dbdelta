"""Assess the danger of each change through a registry of independent rules."""

from dbdelta.risk import rules as _rules  # noqa: F401  (registers the built-in rules)
from dbdelta.risk.context import DEFAULT_LARGE_TABLE_ROWS, RiskContext
from dbdelta.risk.findings import Finding, Level
from dbdelta.risk.registry import Rule, assess, change_rule, registered_rules, rule
from dbdelta.risk.reversibility import Irreversible, irreversible_changes, keeps_values

__all__ = [
    "DEFAULT_LARGE_TABLE_ROWS",
    "Finding",
    "Irreversible",
    "Level",
    "RiskContext",
    "Rule",
    "assess",
    "change_rule",
    "irreversible_changes",
    "keeps_values",
    "registered_rules",
    "rule",
]
