"""The queries risk findings suggest must run, and findings must match what the plan does.

Queries run before the migration, so they may only use names the database already has:
each pair is assessed with and without rename detection, whose findings use new names.
"""

import sqlite3
from dataclasses import replace

import psycopg
import pytest
from tests.support.databases import load_sqlite_connection
from tests.support.fixtures import FixturePair

from dbdelta.cli.analysis import Migration, migrate
from dbdelta.cli.config import Settings
from dbdelta.dialects import Dialect, name_key
from dbdelta.diff import RenameTable
from dbdelta.loaders import load_ddl
from dbdelta.plan import RebuildTable, plan_migration

SQLITE = Dialect.SQLITE
PG = Dialect.POSTGRESQL

RENAMES = pytest.mark.parametrize("detect_renames", [False, True], ids=["drops", "renames"])


def check_queries(migration: Migration) -> list[str]:
    return [
        query
        for finding in migration.findings
        if finding.check_sql
        for query in finding.check_sql.split(";\n")
    ]


@RENAMES
def test_sqlite_findings(sqlite_pair: FixturePair, detect_renames: bool) -> None:
    settings = replace(sqlite_pair.settings, detect_renames=detect_renames)
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sqlite_pair.a + (sqlite_pair.seed or ""))
        source = load_sqlite_connection(connection).schema
        target = load_ddl(sqlite_pair.b, SQLITE).schema
        migration = migrate(source, target, SQLITE, settings)

        for query in check_queries(migration):
            connection.execute(query).fetchall()

        plan = plan_migration(migration.changes, source, target, SQLITE)
        rebuilt = {
            name_key(operation.old.name, SQLITE)
            for operation in plan.operations
            if isinstance(operation, RebuildTable)
        }
        reported = {
            name_key(finding.subject.removeprefix("table "), SQLITE)
            for finding in migration.findings
            if finding.rule == "sqlite-rebuild"
        }
        assert reported == rebuilt
    finally:
        connection.close()


@RENAMES
@pytest.mark.postgres
def test_postgres_check_queries_run(
    postgres_pair: FixturePair, postgres: psycopg.Connection, detect_renames: bool
) -> None:
    settings = replace(postgres_pair.settings, detect_renames=detect_renames)
    postgres.execute(postgres_pair.a + (postgres_pair.seed or ""))
    source = load_ddl(postgres_pair.a, PG).schema
    target = load_ddl(postgres_pair.b, PG).schema

    for query in check_queries(migrate(source, target, PG, settings)):
        postgres.execute(query).fetchall()


def test_check_queries_use_the_names_before_renames() -> None:
    source = load_ddl(
        "CREATE TABLE users (id int PRIMARY KEY, nick text, email text, bio text)", PG
    ).schema
    target = load_ddl(
        "CREATE TABLE app_users"
        " (id int PRIMARY KEY, nick_name text NOT NULL, email text, bio text)",
        PG,
    ).schema
    settings = Settings(detect_renames=True)

    migration = migrate(source, target, PG, settings)

    assert isinstance(migration.changes[0], RenameTable)
    assert check_queries(migration) == ['SELECT count(*) FROM "users" WHERE "users"."nick" IS NULL']
