import pytest

from dbdelta.cli.markdown import code, escape, fenced


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("drop table legacy_scores", r"drop table legacy\_scores"),
        ("a | b", r"a \| b"),
        ("<script>", r"\<script>"),
        ("[x](http://example.com)", r"\[x\](http://example.com)"),
        ("`x` *y* ~z~ &amp;", r"\`x\` \*y\* \~z\~ \&amp;"),
        ("two\nlines", "two lines"),
    ],
)
def test_escape_keeps_text_literal_on_one_line(text: str, escaped: str) -> None:
    assert escape(text) == escaped


@pytest.mark.parametrize(
    ("text", "span"),
    [
        ("a.sql", "`a.sql`"),
        ("my `odd` file.sql", "``my `odd` file.sql``"),
        ("`start", "`` `start ``"),
    ],
)
def test_code_spans_outlast_backticks_inside(text: str, span: str) -> None:
    assert code(text) == span


def test_fences_outlast_backtick_runs_inside() -> None:
    assert fenced("SELECT 1\n", "sql") == "```sql\nSELECT 1\n```"
    assert fenced("-- ````\nSELECT 1", "sql") == "`````sql\n-- ````\nSELECT 1\n`````"
