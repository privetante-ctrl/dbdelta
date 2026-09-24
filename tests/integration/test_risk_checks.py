"""The queries risk findings suggest must run, and findings must match what the plan does."""

import sqlite3

import psycopg
import pytest
from tests.support.databases import load_sqlite_connection
from tests.support.fixtures import FixturePair

from dbdelta.dialects import Dialect, name_key
from dbdelta.diff import diff_schemas
from dbdelta.loaders import load_ddl
from dbdelta.plan import RebuildTable, plan_migration
from dbdelta.risk import Finding, RiskContext, assess

SQLITE = Dialect.SQLITE
PG = Dialect.POSTGRESQL


def check_queries(findings: tuple[Finding, ...]) -> list[str]:
    return [
        query
        for finding in findings
        if finding.check_sql
        for query in finding.check_sql.split(";\n")
    ]


def test_sqlite_findings(sqlite_pair: FixturePair) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(sqlite_pair.a + (sqlite_pair.seed or ""))
        source = load_sqlite_connection(connection).schema
        target = load_ddl(sqlite_pair.b, SQLITE).schema
        changes = diff_schemas(source, target, SQLITE)
        findings = assess(changes, RiskContext(SQLITE, source, target))

        for query in check_queries(findings):
            connection.execute(query).fetchall()

        plan = plan_migration(changes, source, target, SQLITE)
        rebuilt = {
            name_key(operation.old.name, SQLITE)
            for operation in plan.operations
            if isinstance(operation, RebuildTable)
        }
        reported = {
            name_key(finding.subject.removeprefix("table "), SQLITE)
            for finding in findings
            if finding.rule == "sqlite-rebuild"
        }
        assert reported == rebuilt
    finally:
        connection.close()


@pytest.mark.postgres
def test_postgres_check_queries_run(
    postgres_pair: FixturePair, postgres: psycopg.Connection
) -> None:
    postgres.execute(postgres_pair.a + (postgres_pair.seed or ""))
    source = load_ddl(postgres_pair.a, PG).schema
    target = load_ddl(postgres_pair.b, PG).schema
    findings = assess(diff_schemas(source, target, PG), RiskContext(PG, source, target))

    for query in check_queries(findings):
        postgres.execute(query).fetchall()
