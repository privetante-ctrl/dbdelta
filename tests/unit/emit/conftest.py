from collections.abc import Callable

import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.emit import EmitOptions, Script, emit_migration
from dbdelta.loaders import load_ddl
from dbdelta.plan import plan_migration

Migrate = Callable[..., Script]


@pytest.fixture
def migrate() -> Migrate:
    """Build the migration script between two DDL snippets."""

    def build(
        before: str,
        after: str,
        dialect: Dialect = Dialect.POSTGRESQL,
        options: EmitOptions | None = None,
    ) -> Script:
        source = load_ddl(before, dialect).schema
        target = load_ddl(after, dialect).schema
        changes = diff_schemas(source, target, dialect)
        return emit_migration(plan_migration(changes, source, target, dialect), options)

    return build
