import pytest

from dbdelta.cli.analysis import DEFAULT_DIALECT, resolve_dialect, without_tables
from dbdelta.dialects import Dialect
from dbdelta.loaders import LoadError, load_ddl

SCHEMA = """
CREATE TABLE users (id int);
CREATE TABLE django_session (id int);
CREATE TABLE Django_Admin_Log (id int);
"""


def test_urls_decide_the_dialect() -> None:
    sources = ("a.sql", "sqlite:///app.db")

    assert resolve_dialect(sources, None) is Dialect.SQLITE
    assert resolve_dialect(sources, Dialect.SQLITE) is Dialect.SQLITE


def test_files_use_the_configured_dialect_or_the_default() -> None:
    assert resolve_dialect(("a.sql", "b.sql"), Dialect.SQLITE) is Dialect.SQLITE
    assert resolve_dialect(("a.sql", "b.sql"), None) is DEFAULT_DIALECT


def test_databases_of_different_dialects_cannot_be_compared() -> None:
    with pytest.raises(LoadError, match="cannot compare postgresql and sqlite databases"):
        resolve_dialect(("postgresql://db/app", "sqlite:///app.db"), None)


def test_a_dialect_that_contradicts_a_url_is_an_error() -> None:
    with pytest.raises(LoadError, match="--dialect sqlite does not match the postgresql"):
        resolve_dialect(("postgresql://db/app", "b.sql"), Dialect.SQLITE)


def test_ignored_tables_match_shell_patterns() -> None:
    schema = load_ddl(SCHEMA, Dialect.POSTGRESQL).schema

    kept = without_tables(schema, ["django_*"], Dialect.POSTGRESQL)

    # PostgreSQL folds the unquoted Django_Admin_Log to lower case when it loads it.
    assert [table.name for table in kept.tables] == ["users"]
    assert without_tables(schema, [], Dialect.POSTGRESQL) is schema


def test_ignored_tables_match_case_insensitively_in_sqlite() -> None:
    schema = load_ddl(SCHEMA, Dialect.SQLITE).schema

    kept = without_tables(schema, ["DJANGO_*"], Dialect.SQLITE)

    assert [table.name for table in kept.tables] == ["users"]


def test_quoted_names_match_case_sensitively_in_postgresql() -> None:
    schema = load_ddl('CREATE TABLE "Audit" (id int);', Dialect.POSTGRESQL).schema

    assert without_tables(schema, ["audit"], Dialect.POSTGRESQL) == schema
    assert without_tables(schema, ["Audit"], Dialect.POSTGRESQL).tables == ()
