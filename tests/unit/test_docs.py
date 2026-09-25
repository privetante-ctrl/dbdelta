"""The documentation shows what dbdelta really has and prints."""

import re
from pathlib import Path

import pytest

from dbdelta.risk import registered_rules

ROOT = Path(__file__).parents[2]
# A rule row names the rule, then its level: | `drop-table` | danger | ...
_RULE_ROW = re.compile(r"^\| `([a-z-]+)` \| (?:danger|warning|info)", re.MULTILINE)
_FENCE = re.compile(r"^```(text|sql)\n(.*?)^```", re.MULTILINE | re.DOTALL)


@pytest.mark.parametrize("document", ["README.md", "docs/ARCHITECTURE.md"])
def test_rule_tables_list_every_rule(document: str) -> None:
    rows = _RULE_ROW.findall((ROOT / document).read_text(encoding="utf-8"))

    assert sorted(rows) == [rule.code for rule in registered_rules()]


def test_quick_start_shows_real_output() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    printed = {
        line.rstrip()
        for path in (ROOT / "examples" / "shop" / "output").iterdir()
        for line in path.read_text(encoding="utf-8").splitlines()
    }

    shown = [
        line.rstrip()
        for _, block in _FENCE.findall(quick_start)
        for line in block.splitlines()
        if line.strip() not in ("", "...")
    ]

    assert shown
    assert [line for line in shown if line not in printed] == []
