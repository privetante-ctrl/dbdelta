"""Invariants of the pure layers for any schema."""

import pytest
from hypothesis import given
from tests.support.strategies import schema_pairs, schemas

from dbdelta.cli.analysis import migrate
from dbdelta.cli.config import Settings
from dbdelta.dialects import Dialect
from dbdelta.diff import RenameColumn, RenameTable, diff_schemas, possible_renames
from dbdelta.loaders import load_ddl
from dbdelta.model import Schema

DIALECTS = pytest.mark.parametrize("dialect", list(Dialect))


@DIALECTS
@given(schema=schemas())
def test_a_schema_does_not_differ_from_itself(dialect: Dialect, schema: Schema) -> None:
    assert diff_schemas(schema, schema, dialect, strict_column_order=True) == ()


@DIALECTS
@given(schema=schemas())
def test_the_sql_that_creates_a_schema_loads_back_into_it(dialect: Dialect, schema: Schema) -> None:
    script = migrate(Schema(), schema, dialect, Settings()).script

    loaded = load_ddl(script.render(), dialect)

    assert loaded.warnings == ()
    assert diff_schemas(loaded.schema, schema, dialect, strict_column_order=True) == ()


@DIALECTS
@given(pair=schema_pairs())
def test_renames_found_in_reverse_are_the_reverse_renames(
    dialect: Dialect, pair: tuple[Schema, Schema]
) -> None:
    old, new = pair

    forward = possible_renames(diff_schemas(old, new, dialect))
    backward = possible_renames(diff_schemas(new, old, dialect))

    assert sorted(map(_reversed, (candidate.rename for candidate in forward)), key=repr) == sorted(
        (candidate.rename for candidate in backward), key=repr
    )


def _reversed(rename: RenameTable | RenameColumn) -> RenameTable | RenameColumn:
    if isinstance(rename, RenameTable):
        return RenameTable(rename.new_name, rename.table)
    return RenameColumn(rename.table, rename.new_name, rename.column)
