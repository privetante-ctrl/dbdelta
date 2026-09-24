import random
from typing import get_args

import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import (
    AddForeignKey,
    AddTable,
    diff_schemas,
)
from dbdelta.loaders import load_ddl
from dbdelta.plan import (
    Operation,
    RebuildTable,
    ReplaceEnum,
    describe_operation,
    plan_migration,
)
from dbdelta.plan.planner import _PHASES

PG = Dialect.POSTGRESQL
SQLITE = Dialect.SQLITE


def plan(before: str, after: str, dialect: Dialect = PG) -> list[Operation]:
    source = load_ddl(before, dialect).schema
    target = load_ddl(after, dialect).schema
    changes = diff_schemas(source, target, dialect)
    return list(plan_migration(changes, source, target, dialect).operations)


def steps(before: str, after: str, dialect: Dialect = PG) -> list[str]:
    return [describe_operation(operation) for operation in plan(before, after, dialect)]


def test_every_operation_type_has_a_phase() -> None:
    assert set(get_args(Operation)) == set(_PHASES)


def test_no_changes_make_an_empty_plan() -> None:
    assert plan("CREATE TABLE t (a int)", "CREATE TABLE t (a int)") == []


def test_operations_run_in_phases() -> None:
    before = """
        CREATE TYPE old_mood AS ENUM ('a');
        CREATE TYPE mood AS ENUM ('a');
        CREATE TABLE gone (id int PRIMARY KEY);
        CREATE TABLE users (id int PRIMARY KEY, legacy text, name text DEFAULT 'x', m old_mood,
                            gone_id int REFERENCES gone, CHECK (id > 0));
        CREATE INDEX ix_legacy ON users (legacy);
    """
    after = """
        CREATE TYPE mood AS ENUM ('a', 'b');
        CREATE TYPE new_mood AS ENUM ('x');
        CREATE TABLE orgs (id int PRIMARY KEY);
        CREATE TABLE users (id int PRIMARY KEY, name varchar(10) NOT NULL DEFAULT 'y',
                            m new_mood, org_id int REFERENCES orgs, email text UNIQUE,
                            CHECK (id >= 0));
        CREATE INDEX ix_email ON users (email);
    """

    assert steps(before, after) == [
        "drop foreign key users (gone_id) -> gone (id)",
        'drop check constraint on users ("id" > 0)',
        "drop index ix_legacy on users (legacy)",
        "drop column users.gone_id",
        "drop column users.legacy",
        "drop table gone",
        "change values of enum type mood from ('a') to ('a', 'b')",
        "create enum type new_mood ('x')",
        "create table orgs",
        "add column users.org_id integer",
        "add column users.email text",
        "drop default of users.name",
        "change type of users.m from old_mood to new_mood",
        "change type of users.name from text to varchar(10)",
        "make users.name NOT NULL",
        "set default of users.name to 'y'",
        'add check constraint on users ("id" >= 0)',
        "add unique constraint on users (email)",
        "create index ix_email on users (email)",
        "add foreign key users (org_id) -> orgs (id)",
        "drop enum type old_mood",
    ]


CHAIN = """
    CREATE TABLE c (id int PRIMARY KEY);
    CREATE TABLE b (id int PRIMARY KEY, c_id int REFERENCES c);
    CREATE TABLE a (b_id int REFERENCES b);
"""


def test_tables_are_created_after_the_tables_they_reference() -> None:
    assert steps("", CHAIN) == ["create table c", "create table b", "create table a"]


def test_tables_are_dropped_before_the_tables_they_reference() -> None:
    assert steps(CHAIN, "") == ["drop table a", "drop table b", "drop table c"]


def cycle_ddl() -> str:
    # The DDL loader applies statements in order, so the cycle is closed with ALTER TABLE.
    return (
        "CREATE TABLE a (id int PRIMARY KEY, b_id int);"
        "CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);"
        "ALTER TABLE a ADD FOREIGN KEY (b_id) REFERENCES b;"
    )


def test_cyclic_foreign_keys_are_added_after_the_tables_in_postgresql() -> None:
    operations = plan("", cycle_ddl())

    assert [describe_operation(operation) for operation in operations] == [
        "create table a",
        "create table b",
        "add foreign key a (b_id) -> b (id)",
    ]
    first = operations[0]
    assert isinstance(first, AddTable)
    assert first.table.foreign_keys == ()
    second = operations[1]
    assert isinstance(second, AddTable)
    assert len(second.table.foreign_keys) == 1


def test_cyclic_foreign_keys_stay_inline_in_sqlite() -> None:
    operations = plan("", cycle_ddl(), SQLITE)

    assert [describe_operation(operation) for operation in operations] == [
        "create table a",
        "create table b",
    ]
    assert all(
        isinstance(operation, AddTable) and operation.table.foreign_keys for operation in operations
    )


def test_dropping_cyclic_tables_releases_the_cycle_first_in_postgresql() -> None:
    assert steps(cycle_ddl(), "") == [
        "drop foreign key a (b_id) -> b (id)",
        "drop table b",
        "drop table a",
    ]
    assert steps(cycle_ddl(), "", SQLITE) == ["drop table b", "drop table a"]


def test_self_references_stay_inline() -> None:
    operations = plan("", "CREATE TABLE tree (id int PRIMARY KEY, parent int REFERENCES tree)")

    assert len(operations) == 1
    assert isinstance(operations[0], AddTable)
    assert len(operations[0].table.foreign_keys) == 1


REFERENCED_KEY = """
    CREATE TABLE users (id int, CONSTRAINT {} PRIMARY KEY (id));
    CREATE TABLE orders (user_id int REFERENCES users (id));
"""


def test_foreign_keys_are_rebuilt_around_a_replaced_key_in_postgresql() -> None:
    before, after = REFERENCED_KEY.format("users_pk"), REFERENCED_KEY.format("users_pkey")

    assert steps(before, after) == [
        "drop foreign key orders (user_id) -> users (id)",
        "drop primary key users_pk on users (id)",
        "add primary key users_pkey on users (id)",
        "add foreign key orders (user_id) -> users (id)",
    ]
    assert steps(before, after, SQLITE) == ["rebuild table users"]


def test_foreign_keys_are_rebuilt_around_a_replaced_unique_index() -> None:
    template = """
        CREATE TABLE users (id int, email text);
        CREATE UNIQUE INDEX {} ON users (email);
        CREATE TABLE orders (email text REFERENCES users (email));
    """

    assert steps(template.format("ux_old"), template.format("ux_new")) == [
        "drop foreign key orders (email) -> users (email)",
        "drop unique index ux_old on users (email)",
        "create unique index ux_new on users (email)",
        "add foreign key orders (email) -> users (email)",
    ]


def test_new_table_waits_for_a_key_added_to_an_existing_table() -> None:
    before = "CREATE TABLE orgs (id int PRIMARY KEY, code text)"
    after = (
        "CREATE TABLE orgs (id int PRIMARY KEY, code text UNIQUE);"
        "CREATE TABLE members (org_code text REFERENCES orgs (code))"
    )

    assert steps(before, after) == [
        "create table members",
        "add unique constraint on orgs (code)",
        "add foreign key members (org_code) -> orgs (code)",
    ]
    assert steps(before, after, SQLITE) == ["create table members", "rebuild table orgs"]


def test_foreign_keys_to_existing_keys_stay_inline() -> None:
    operations = plan(
        "CREATE TABLE orgs (id int PRIMARY KEY)",
        "CREATE TABLE orgs (id int PRIMARY KEY); CREATE TABLE m (org int REFERENCES orgs)",
    )

    assert [type(operation) for operation in operations] == [AddTable]


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            "CREATE TABLE t (a int DEFAULT 1)",
            "CREATE TABLE t (a text DEFAULT 'x')",
            [
                "drop default of t.a",
                "change type of t.a from integer to text",
                "set default of t.a to 'x'",
            ],
        ),
        (
            "CREATE TABLE t (a int DEFAULT 1)",
            "CREATE TABLE t (a bigint DEFAULT 1)",
            ["change type of t.a from integer to bigint"],
        ),
        (
            "CREATE TABLE t (a int NOT NULL)",
            "CREATE TABLE t (a text DEFAULT 'x')",
            [
                "allow NULL in t.a",
                "change type of t.a from integer to text",
                "set default of t.a to 'x'",
            ],
        ),
    ],
)
def test_column_changes_are_ordered_within_a_column(
    before: str, after: str, expected: list[str]
) -> None:
    assert steps(before, after) == expected


def test_plan_does_not_depend_on_the_order_of_changes() -> None:
    before = "CREATE TABLE t (a int, b int); CREATE INDEX ix ON t (a)"
    after = (
        "CREATE TABLE t (a bigint NOT NULL, c int UNIQUE); CREATE TABLE u (x int);"
        "CREATE INDEX ix ON t (c)"
    )
    source = load_ddl(before, PG).schema
    changes = list(diff_schemas(source, load_ddl(after, PG).schema, PG))
    shuffled = changes[:]
    random.Random(7).shuffle(shuffled)

    assert shuffled != changes
    target = load_ddl(after, PG).schema
    assert plan_migration(shuffled, source, target, PG) == plan_migration(
        changes, source, target, PG
    )


def test_sqlite_matches_referenced_tables_case_insensitively() -> None:
    operations = plan(
        "",
        "CREATE TABLE Parent (id INTEGER PRIMARY KEY);CREATE TABLE child (p INT REFERENCES PARENT)",
        SQLITE,
    )

    assert [describe_operation(operation) for operation in operations] == [
        "create table Parent",
        "create table child",
    ]
    assert not any(isinstance(operation, AddForeignKey) for operation in operations)


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (
            "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT, b INT DEFAULT 0, c TEXT);"
            "CREATE INDEX ix_a ON t (a)",
            ["add column t.b integer DEFAULT 0", "add column t.c text"],
        ),
        (
            "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT, b INT NOT NULL DEFAULT 0);"
            "CREATE INDEX ix_a ON t (a)",
            ["add column t.b integer NOT NULL DEFAULT 0"],
        ),
        (
            "CREATE TABLE t (id INTEGER PRIMARY KEY)",
            ["drop index ix_a on t (a)", "drop column t.a"],
        ),
        (
            "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT); CREATE INDEX ix_a ON t (a DESC)",
            ["drop index ix_a on t (a)", "create index ix_a on t (a DESC)"],
        ),
    ],
)
def test_sqlite_alters_in_place_what_alter_table_supports(after: str, expected: list[str]) -> None:
    before = "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT); CREATE INDEX ix_a ON t (a)"

    assert steps(before, after, SQLITE) == expected


@pytest.mark.parametrize(
    "after",
    [
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a INT)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT NOT NULL)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT DEFAULT 'x')",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT UNIQUE)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT CHECK (a <> ''))",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT REFERENCES t)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, a TEXT)",
        "CREATE TABLE t (id INTEGER, a TEXT)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT, b INT NOT NULL)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT, b TEXT DEFAULT CURRENT_TIMESTAMP)",
    ],
)
def test_sqlite_rebuilds_tables_it_cannot_alter(after: str) -> None:
    before = "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT)"

    operations = plan(before, after, SQLITE)

    assert len(operations) == 1
    rebuild = operations[0]
    assert isinstance(rebuild, RebuildTable)
    assert rebuild.old == load_ddl(before, SQLITE).schema.tables[0]
    assert rebuild.new == load_ddl(after, SQLITE).schema.tables[0]
    assert rebuild.changes


def test_a_rebuild_absorbs_index_changes_of_its_table() -> None:
    before = "CREATE TABLE t (a INT, b INT); CREATE INDEX ix ON t (a)"
    after = "CREATE TABLE t (a TEXT, b INT); CREATE INDEX ix2 ON t (b)"

    assert steps(before, after, SQLITE) == ["rebuild table t"]


def test_extending_an_enum_adds_values_in_place() -> None:
    operations = plan(
        "CREATE TYPE mood AS ENUM ('sad', 'happy')",
        "CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy', 'great')",
    )

    assert [type(operation).__name__ for operation in operations] == ["AlterEnum"]


def test_removing_enum_values_recreates_the_type_and_its_columns() -> None:
    before = """
        CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
        CREATE TABLE t (a mood, b mood DEFAULT 'ok', c text, gone mood);
        CREATE TABLE u (m mood);
    """
    after = """
        CREATE TYPE mood AS ENUM ('happy', 'sad');
        CREATE TABLE t (a mood, b mood DEFAULT 'sad', c text);
    """

    operations = plan(before, after)

    replace = next(operation for operation in operations if isinstance(operation, ReplaceEnum))
    assert replace.new.values == ("happy", "sad")
    assert [(table, column.name, column.default) for table, column in replace.columns] == [
        ("t", "a", None),
        ("t", "b", "'sad'"),
    ]
    order = [describe_operation(operation) for operation in operations]
    assert order.index("drop column t.gone") < order.index(describe_operation(replace))
    assert order.index("drop table u") < order.index(describe_operation(replace))


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            "CREATE TABLE t (a int)",
            "CREATE TABLE t (a int GENERATED ALWAYS AS IDENTITY)",
            ["make t.a NOT NULL", "change identity of t.a from none to always"],
        ),
        (
            "CREATE TABLE t (a int GENERATED ALWAYS AS IDENTITY)",
            "CREATE TABLE t (a int)",
            ["change identity of t.a from always to none", "allow NULL in t.a"],
        ),
    ],
)
def test_identity_changes_respect_not_null(before: str, after: str, expected: list[str]) -> None:
    assert steps(before, after) == expected
