from collections.abc import Callable

import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import AlterIdentity, ReorderColumns
from dbdelta.emit import EmitOptions, Script
from dbdelta.emit.postgresql import PostgresEmitter
from dbdelta.model import Column, DataType, Identity, Schema, Table
from dbdelta.plan import MigrationPlan, RebuildTable

Migrate = Callable[..., Script]
EMITTER = PostgresEmitter()


def sql(script: Script) -> list[str]:
    return [statement.sql for statement in script.statements() if statement.sql]


@pytest.mark.parametrize(
    ("data_type", "expected"),
    [
        (DataType("integer"), "integer"),
        (DataType("double precision"), "double precision"),
        (DataType("numeric", (10, 2)), "numeric(10,2)"),
        (DataType("varchar", (20,), is_array=True), "varchar(20)[]"),
        (DataType("mood"), '"mood"'),
        (DataType("Mood"), '"Mood"'),
        (DataType("audit.mood"), '"audit"."mood"'),
        (DataType("geometry(point,4326)"), "geometry(point,4326)"),
    ],
)
def test_type_spelling(data_type: DataType, expected: str) -> None:
    assert EMITTER.type_sql(data_type) == expected


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (
            Column("id", DataType("bigint"), False, identity=Identity.SERIAL),
            '"id" bigserial NOT NULL',
        ),
        (
            Column("id", DataType("integer"), False, identity=Identity.ALWAYS),
            '"id" integer NOT NULL GENERATED ALWAYS AS IDENTITY',
        ),
        (
            Column("n", DataType("text"), default="'x'"),
            "\"n\" text DEFAULT 'x'",
        ),
    ],
)
def test_column_definitions(column: Column, expected: str) -> None:
    assert EMITTER.column_sql(column) == expected


def test_create_table_with_constraints_and_indexes(migrate: Migrate) -> None:
    script = migrate(
        "CREATE TABLE orgs (id int PRIMARY KEY)",
        """
        CREATE TABLE orgs (id int PRIMARY KEY);
        CREATE TABLE users (
            id int CONSTRAINT users_pk PRIMARY KEY,
            email text NOT NULL UNIQUE,
            org int REFERENCES orgs ON DELETE CASCADE,
            CHECK (email <> '')
        );
        CREATE INDEX ix_org ON users USING hash (org);
        """,
    )

    assert sql(script) == [
        'CREATE TABLE "users" (\n'
        '    "id" integer NOT NULL,\n'
        '    "email" text NOT NULL,\n'
        '    "org" integer,\n'
        '    CONSTRAINT "users_pk" PRIMARY KEY ("id"),\n'
        '    UNIQUE ("email"),\n'
        "    CHECK (\"email\" <> ''),\n"
        '    FOREIGN KEY ("org") REFERENCES "orgs" ("id") ON DELETE CASCADE\n'
        ")",
        'CREATE INDEX "ix_org" ON "users" USING hash ("org")',
    ]


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("int", "bigint", 'ALTER TABLE "t" ALTER COLUMN "a" TYPE bigint'),
        ("text", "int", 'ALTER TABLE "t" ALTER COLUMN "a" TYPE integer USING "a"::integer'),
        ("mood", "text", 'ALTER TABLE "t" ALTER COLUMN "a" TYPE text'),
        ("mood", "mood2", 'ALTER TABLE "t" ALTER COLUMN "a" TYPE "mood2" USING "a"::text::"mood2"'),
    ],
)
def test_type_changes_add_using_only_when_needed(
    migrate: Migrate, old: str, new: str, expected: str
) -> None:
    enums = "CREATE TYPE mood AS ENUM ('a'); CREATE TYPE mood2 AS ENUM ('a');"

    script = migrate(f"{enums} CREATE TABLE t (a {old})", f"{enums} CREATE TABLE t (a {new})")

    assert sql(script) == [expected]


def test_unnamed_constraints_are_dropped_by_their_default_names(migrate: Migrate) -> None:
    script = migrate(
        "CREATE TABLE p (id int PRIMARY KEY);"
        "CREATE TABLE t (a int PRIMARY KEY, b int UNIQUE, c int REFERENCES p, CHECK (b > c),"
        " CHECK (a > 0));"
        "CREATE INDEX ON t (lower(b::text), c)",
        "CREATE TABLE p (id int PRIMARY KEY); CREATE TABLE t (a int, b int, c int)",
    )

    assert sql(script) == [
        'ALTER TABLE "t" DROP CONSTRAINT "t_c_fkey"',
        'ALTER TABLE "t" DROP CONSTRAINT "t_a_check"',
        'ALTER TABLE "t" DROP CONSTRAINT "t_check"',
        'DROP INDEX "t_lower_c_idx"',
        'ALTER TABLE "t" DROP CONSTRAINT "t_pkey"',
        'ALTER TABLE "t" DROP CONSTRAINT "t_b_key"',
        'ALTER TABLE "t" ALTER COLUMN "a" DROP NOT NULL',
    ]


def test_new_enum_values_are_committed_before_the_main_transaction(migrate: Migrate) -> None:
    script = migrate(
        "CREATE TYPE mood AS ENUM ('ok'); CREATE TABLE t (m mood)",
        "CREATE TYPE mood AS ENUM ('sad', 'ok', 'great', 'best');"
        "CREATE TABLE t (m mood DEFAULT 'great')",
    )

    assert [(block.transactional, len(block.statements)) for block in script.blocks] == [
        (True, 3),
        (True, 1),
    ]
    assert sql(script) == [
        "ALTER TYPE \"mood\" ADD VALUE 'sad' BEFORE 'ok'",
        "ALTER TYPE \"mood\" ADD VALUE 'great' AFTER 'ok'",
        "ALTER TYPE \"mood\" ADD VALUE 'best' AFTER 'great'",
        'ALTER TABLE "t" ALTER COLUMN "m" SET DEFAULT \'great\'',
    ]


def test_reduced_enum_is_recreated_and_columns_converted(migrate: Migrate) -> None:
    script = migrate(
        "CREATE TYPE mood AS ENUM ('sad', 'ok'); CREATE TABLE t (m mood DEFAULT 'ok', l mood[])",
        "CREATE TYPE mood AS ENUM ('ok'); CREATE TABLE t (m mood DEFAULT 'ok', l mood[])",
    )

    assert sql(script) == [
        'ALTER TYPE "mood" RENAME TO "mood__dbdelta_old"',
        "CREATE TYPE \"mood\" AS ENUM ('ok')",
        'ALTER TABLE "t" ALTER COLUMN "m" DROP DEFAULT',
        'ALTER TABLE "t" ALTER COLUMN "m" TYPE "mood" USING "m"::text::"mood"',
        'ALTER TABLE "t" ALTER COLUMN "m" SET DEFAULT \'ok\'',
        'ALTER TABLE "t" ALTER COLUMN "l" TYPE "mood"[] USING "l"::text[]::"mood"[]',
        'DROP TYPE "mood__dbdelta_old"',
    ]


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "int NOT NULL",
            "int GENERATED ALWAYS AS IDENTITY",
            [
                "ADD GENERATED ALWAYS AS IDENTITY",
                "SELECT setval(pg_get_serial_sequence('\"t\"', 'a'),"
                ' COALESCE(MAX("a"), 0) + 1, false) FROM "t"',
            ],
        ),
        ("int GENERATED ALWAYS AS IDENTITY", "int NOT NULL", ["DROP IDENTITY"]),
        (
            "int GENERATED ALWAYS AS IDENTITY",
            "int GENERATED BY DEFAULT AS IDENTITY",
            ["SET GENERATED BY DEFAULT"],
        ),
        ("serial", "int NOT NULL", ["DROP DEFAULT"]),
        (
            "serial",
            "int GENERATED BY DEFAULT AS IDENTITY",
            [
                "DROP DEFAULT",
                "ADD GENERATED BY DEFAULT AS IDENTITY",
                "SELECT setval(pg_get_serial_sequence('\"t\"', 'a'),"
                ' COALESCE(MAX("a"), 0) + 1, false) FROM "t"',
            ],
        ),
        (
            "int GENERATED ALWAYS AS IDENTITY",
            "serial",
            [
                "DROP IDENTITY",
                'CREATE SEQUENCE "t_a_seq" AS integer OWNED BY "t"."a"',
                'SELECT setval(\'"t_a_seq"\', COALESCE(MAX("a"), 0) + 1, false) FROM "t"',
                "SET DEFAULT nextval('\"t_a_seq\"'::regclass)",
            ],
        ),
    ],
)
def test_identity_changes(migrate: Migrate, old: str, new: str, expected: list[str]) -> None:
    statements = sql(migrate(f"CREATE TABLE t (a {old})", f"CREATE TABLE t (a {new})"))

    prefix = 'ALTER TABLE "t" ALTER COLUMN "a" '
    assert [statement.removeprefix(prefix) for statement in statements] == expected


def test_concurrent_indexes_run_outside_the_transaction(migrate: Migrate) -> None:
    before = """
        CREATE TABLE users (id int PRIMARY KEY, email text, name text);
        CREATE UNIQUE INDEX ux_email ON users (email);
        CREATE INDEX ix_name ON users (name);
        CREATE TABLE refs (email text REFERENCES users (email));
    """
    after = """
        CREATE TABLE users (id int PRIMARY KEY, email text, name text, age int);
        CREATE UNIQUE INDEX ux_email ON users (email);
        CREATE INDEX ix_age ON users (age);
        CREATE TABLE refs (email text REFERENCES users (email));
    """

    script = migrate(before, after, options=EmitOptions(concurrent_indexes=True))

    assert [
        (block.transactional, [statement.sql for statement in block.statements])
        for block in script.blocks
    ] == [
        (False, ['DROP INDEX CONCURRENTLY "ix_name"']),
        (True, ['ALTER TABLE "users" ADD COLUMN "age" integer']),
        (False, ['CREATE INDEX CONCURRENTLY "ix_age" ON "users" ("age")']),
    ]


def test_unique_index_backing_a_foreign_key_is_not_built_concurrently(migrate: Migrate) -> None:
    template = """
        CREATE TABLE users (id int PRIMARY KEY, email text);
        CREATE UNIQUE INDEX {} ON users (email);
        CREATE TABLE refs (email text REFERENCES users (email));
    """

    script = migrate(
        template.format("ux_old"),
        template.format("ux_new"),
        options=EmitOptions(concurrent_indexes=True),
    )

    assert len(script.blocks) == 1
    assert not any("CONCURRENTLY" in statement.sql for statement in script.statements())


def test_column_order_changes_are_reported_but_not_applied() -> None:
    change = ReorderColumns("t", ("a", "b"), ("b", "a"))
    plan = MigrationPlan((change,), Schema(), Schema(), Dialect.POSTGRESQL)

    script = EMITTER.emit(plan)

    assert script.is_empty
    assert "-- PostgreSQL cannot reorder columns" in script.render()


def test_rebuilds_are_not_postgresql_operations() -> None:
    table = Table("t", (Column("a", DataType("integer")),))
    plan = MigrationPlan((RebuildTable(table, table, ()),), Schema(), Schema(), Dialect.POSTGRESQL)

    with pytest.raises(ValueError, match="PostgreSQL cannot rebuild table t"):
        EMITTER.emit(plan)


def test_sqlite_identities_are_not_postgresql_identities() -> None:
    change = AlterIdentity("t", "a", None, Identity.AUTOINCREMENT)
    plan = MigrationPlan((change,), Schema(), Schema(), Dialect.POSTGRESQL)

    with pytest.raises(ValueError, match=r"no None or autoincrement identity for t\.a"):
        EMITTER.emit(plan)


def test_emitter_rejects_plans_for_other_dialects() -> None:
    plan = MigrationPlan((), Schema(), Schema(), Dialect.SQLITE)

    with pytest.raises(ValueError, match="cannot write a sqlite migration as postgresql SQL"):
        EMITTER.emit(plan)
