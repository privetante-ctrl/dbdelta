from dbdelta.emit import Block, Script, Statement
from dbdelta.emit.quoting import quote_identifier, quote_literal, quote_qualified


def test_identifiers_are_always_quoted_and_escaped() -> None:
    assert quote_identifier("users") == '"users"'
    assert quote_identifier('we"ird') == '"we""ird"'
    assert quote_qualified("audit.log") == '"audit"."log"'


def test_literals_are_quoted_and_escaped() -> None:
    assert quote_literal("it's") == "'it''s'"
    assert quote_literal("back\\slash") == "'back\\slash'"


def test_script_renders_transactions_and_comments() -> None:
    script = Script(
        (
            Block((Statement("PRAGMA foreign_keys = OFF"),), transactional=False, comment="why"),
            Block(
                (Statement("CREATE TABLE t (a int)", "create table t"), Statement("SELECT 1")),
                transactional=True,
            ),
        )
    )

    assert script.render() == (
        "-- why\n"
        "\n"
        "PRAGMA foreign_keys = OFF;\n"
        "\n"
        "BEGIN;\n"
        "\n"
        "-- create table t\n"
        "CREATE TABLE t (a int);\n"
        "\n"
        "SELECT 1;\n"
        "\n"
        "COMMIT;\n"
    )


def test_notes_render_as_comments_only() -> None:
    script = Script((Block((Statement("", "first line\n\nsecond"),), transactional=False),))

    assert script.render() == "-- first line\n--\n-- second\n"
    assert script.is_empty


def test_empty_script() -> None:
    assert Script().render() == ""
    assert Script().is_empty
