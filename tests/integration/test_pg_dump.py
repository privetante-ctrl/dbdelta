"""A pg_dump of a database must load into the same schema as the database itself."""

import os
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest
from tests.support.databases import POSTGRES_URL_VARIABLE, load_postgres_connection
from tests.support.fixtures import FixturePair

from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.loaders import load_ddl_file

pytestmark = pytest.mark.postgres


def test_dump_loads_like_the_database(
    postgres_pair: FixturePair, postgres: psycopg.Connection, tmp_path: Path
) -> None:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        pytest.skip("pg_dump is not installed")
    # pg_dump refuses to dump a server newer than itself.
    client = subprocess.run([pg_dump, "--version"], capture_output=True, text=True, check=True)
    client_major = int(client.stdout.split()[2].split(".")[0])
    if client_major < postgres.info.server_version // 10000:
        pytest.skip(f"pg_dump {client_major} cannot dump this server")
    postgres.execute(postgres_pair.b)
    row = postgres.execute("SELECT current_schema()").fetchone()
    assert row is not None
    schema = row[0]
    dump = tmp_path / "dump.sql"
    subprocess.run(
        [
            pg_dump,
            os.environ[POSTGRES_URL_VARIABLE],
            "--schema-only",
            f"--schema={schema}",
            "--no-owner",
            f"--file={dump}",
        ],
        check=True,
    )

    from_dump = load_ddl_file(dump, Dialect.POSTGRESQL, schema)
    from_database = load_postgres_connection(postgres)

    assert (
        diff_schemas(
            from_dump.schema, from_database.schema, Dialect.POSTGRESQL, strict_column_order=True
        )
        == ()
    )
