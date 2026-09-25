from collections.abc import Callable

import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import SetNotNull
from dbdelta.emit import Script
from dbdelta.emit.sqlite import SQLiteEmitter
from dbdelta.model import Column, DataType, Schema
from dbdelta.plan import MigrationPlan

Migrate = Callable[..., Script]
SQLITE = Dialect.SQLITE
EMITTER = SQLiteEmitter()


def sql(script: Script) -> list[str]:
    return [statement.sql for statement in script.statements() if statement.sql]


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (Column("a", DataType("")), '"a"'),
        (Column("a", DataType("integer"), False, "0"), '"a" integer NOT NULL DEFAULT 0'),
        (Column("a", DataType("text"), default="'x'"), "\"a\" text DEFAULT 'x'"),
        (
            Column("a", DataType("datetime"), default="DATETIME('now')"),
            "\"a\" datetime DEFAULT (DATETIME('now'))",
        ),
        (
            Column("a", DataType("timestamp"), default="CURRENT_TIMESTAMP"),
            '"a" timestamp DEFAULT (CURRENT_TIMESTAMP)',
        ),
    ],
)
def test_column_definitions(column: Column, expected: str) -> None:
    assert EMITTER.column_sql(column) == expected


def test_autoincrement_keys_are_declared_inline(migrate: Migrate) -> None:
    script = migrate(
        "",
        "CREATE TABLE t (id INTEGER CONSTRAINT t_pk PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)",
        SQLITE,
    )

    assert sql(script) == [
        'CREATE TABLE "t" (\n'
        '    "id" integer NOT NULL CONSTRAINT "t_pk" PRIMARY KEY AUTOINCREMENT,\n'
        '    "name" text,\n'
        '    UNIQUE ("name")\n'
        ")"
    ]


def test_simple_changes_run_in_one_transaction(migrate: Migrate) -> None:
    script = migrate(
        "CREATE TABLE t (a INT, b INT); CREATE INDEX ix_b ON t (b)",
        "CREATE TABLE t (a INT, c TEXT DEFAULT 'x'); CREATE INDEX ix_c ON t (c)",
        SQLITE,
    )

    assert [block.transactional for block in script.blocks] == [True]
    assert sql(script) == [
        'DROP INDEX "ix_b"',
        'ALTER TABLE "t" DROP COLUMN "b"',
        'ALTER TABLE "t" ADD COLUMN "c" text DEFAULT \'x\'',
        'CREATE INDEX "ix_c" ON "t" ("c")',
    ]


def test_tables_are_rebuilt_with_foreign_keys_switched_off(migrate: Migrate) -> None:
    script = migrate(
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a INT, gone TEXT); CREATE INDEX ix_a ON t (a)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, a TEXT NOT NULL, b INT DEFAULT 1);"
        "CREATE INDEX ix_a ON t (a DESC)",
        SQLITE,
    )

    assert [block.transactional for block in script.blocks] == [False, True, False]
    assert sql(script) == [
        "PRAGMA foreign_keys = OFF",
        'CREATE TABLE "_dbdelta_new_t" (\n'
        '    "id" integer NOT NULL,\n'
        '    "a" text NOT NULL,\n'
        '    "b" integer DEFAULT 1,\n'
        '    PRIMARY KEY ("id")\n'
        ")",
        'INSERT INTO "_dbdelta_new_t" ("id", "a") SELECT "id", "a" FROM "t"',
        'DROP TABLE "t"',
        'ALTER TABLE "_dbdelta_new_t" RENAME TO "t"',
        'CREATE INDEX "ix_a" ON "t" ("a" DESC)',
        "PRAGMA foreign_key_check",
        "PRAGMA foreign_keys = ON",
    ]
    rebuild = next(statement for statement in script.statements() if statement.comment)
    assert rebuild.comment is not None
    assert rebuild.comment.startswith("rebuild table t: SQLite cannot make these changes")
    assert "  change type of t.a from integer to text" in rebuild.comment


def test_rebuild_matches_columns_case_insensitively(migrate: Migrate) -> None:
    script = migrate(
        "CREATE TABLE T (ID INTEGER PRIMARY KEY, Name TEXT)",
        "CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT NOT NULL)",
        SQLITE,
    )

    assert 'INSERT INTO "_dbdelta_new_t" ("id", "name") SELECT "ID", "Name" FROM "T"' in sql(script)


def test_changes_that_need_a_rebuild_cannot_be_emitted_in_place() -> None:
    plan = MigrationPlan((SetNotNull("t", "a"),), Schema(), Schema(), SQLITE)

    with pytest.raises(ValueError, match=r"SQLite cannot make t\.a NOT NULL in place"):
        EMITTER.emit(plan)


def test_empty_plan_gives_an_empty_script() -> None:
    assert EMITTER.emit(MigrationPlan((), Schema(), Schema(), SQLITE)).blocks == ()


def test_renames_use_alter_table(migrate: Migrate) -> None:
    before = "CREATE TABLE users (id INTEGER PRIMARY KEY, nick TEXT, email TEXT, bio TEXT)"
    after = "CREATE TABLE app_users (id INTEGER PRIMARY KEY, nick_name TEXT, email TEXT, bio TEXT)"

    script = migrate(before, after, Dialect.SQLITE, detect_renames=True)

    assert [statement.sql for statement in script.statements()] == [
        'ALTER TABLE "users" RENAME TO "app_users"',
        'ALTER TABLE "app_users" RENAME COLUMN "nick" TO "nick_name"',
    ]
