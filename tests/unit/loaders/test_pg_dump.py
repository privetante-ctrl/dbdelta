"""Loading the output of pg_dump --schema-only, stored from PostgreSQL 16."""

from pathlib import Path

import pytest

from dbdelta.dialects import Dialect
from dbdelta.loaders import LoadResult, load_ddl_file
from dbdelta.model import Column, DataType, Identity, ReferentialAction

DUMP = Path(__file__).parents[2] / "fixtures" / "dumps" / "pg_dump_16.sql"


@pytest.fixture(scope="module")
def dump() -> LoadResult:
    return load_ddl_file(DUMP, Dialect.POSTGRESQL, schema="dumped")


def test_serial_columns_are_recognized_from_sequence_ownership(dump: LoadResult) -> None:
    orgs = dump.schema.table("orgs")

    assert orgs is not None
    assert orgs.columns[0] == Column("id", DataType("integer"), False, identity=Identity.SERIAL)


def test_identity_columns_added_by_alter_table(dump: LoadResult) -> None:
    users = dump.schema.table("users")

    assert users is not None
    assert users.columns[0] == Column("id", DataType("bigint"), False, identity=Identity.ALWAYS)


def test_names_in_the_dumped_schema_lose_their_qualifier(dump: LoadResult) -> None:
    users = dump.schema.table("users")

    assert users is not None
    assert dump.schema.enum("mood") is not None
    assert users.column("m") == Column("m", DataType("mood"), default="'ok'")
    assert users.foreign_keys[0].ref_table == "orgs"
    assert users.foreign_keys[0].on_delete is ReferentialAction.CASCADE


def test_conditions_are_read_in_canonical_form(dump: LoadResult) -> None:
    users = dump.schema.table("users")

    assert users is not None
    assert {check.expression.sql for check in users.check_constraints} == {
        '"price" > 0',
        "\"status\" IN ('a', 'b')",
    }
    assert [(index.name, str(index.where)) for index in users.indexes] == [
        ("ux_email", "\"status\" = 'a'")
    ]


def test_only_unsupported_objects_are_reported(dump: LoadResult) -> None:
    assert dump.warnings == (
        "skipped CREATE VIEW v AS SELECT id FROM users: CREATE VIEW is not supported",
    )


def test_a_dump_of_another_schema_loads_nothing_by_default() -> None:
    result = load_ddl_file(DUMP, Dialect.POSTGRESQL)

    assert result.schema.tables == ()
