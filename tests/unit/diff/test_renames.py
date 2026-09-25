import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import (
    Change,
    RenameColumn,
    RenameTable,
    SetNotNull,
    apply_renames,
    diff_schemas,
    names_before_renames,
    possible_renames,
)
from dbdelta.loaders import load_ddl
from dbdelta.model import Expression, Schema

PG = Dialect.POSTGRESQL
SQLITE = Dialect.SQLITE


def schema(ddl: str, dialect: Dialect = PG) -> Schema:
    return load_ddl(ddl, dialect).schema


def renames(before: str, after: str, dialect: Dialect = PG) -> list[tuple[Change, float]]:
    changes = diff_schemas(schema(before, dialect), schema(after, dialect), dialect)
    return [
        (candidate.rename, round(candidate.confidence, 2))
        for candidate in possible_renames(changes)
    ]


def test_columns_of_the_same_type_with_similar_names_may_be_renames() -> None:
    assert renames(
        "CREATE TABLE t (id int, nickname text, fname text)",
        "CREATE TABLE t (id int, nick_name text, first_name text)",
    ) == [
        (RenameColumn("t", "nickname", "nick_name"), 0.96),
        (RenameColumn("t", "fname", "first_name"), 0.8),
    ]


def test_each_column_pairs_once_with_its_most_likely_rename() -> None:
    assert renames(
        "CREATE TABLE t (created date)",
        "CREATE TABLE t (created_at date, created_on date)",
    ) == [(RenameColumn("t", "created", "created_at"), 0.89)]


def test_shape_counts_towards_confidence() -> None:
    same = renames("CREATE TABLE t (code text)", "CREATE TABLE t (kode text)")
    different = renames(
        "CREATE TABLE t (code text)", "CREATE TABLE t (kode text NOT NULL DEFAULT 'x')"
    )

    assert same == [(RenameColumn("t", "code", "kode"), 0.85)]
    assert different == []


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("CREATE TABLE t (nickname text)", "CREATE TABLE t (nick_name varchar(10))"),
        ("CREATE TABLE t (email text)", "CREATE TABLE t (phone text)"),
        ("CREATE TABLE a (x int); CREATE TABLE b (y int)", "CREATE TABLE a (y int)"),
    ],
    ids=["other type", "unrelated name", "other table"],
)
def test_unlike_columns_are_not_renames(before: str, after: str) -> None:
    found = [rename for rename, _ in renames(before, after)]

    assert not any(isinstance(rename, RenameColumn) for rename in found)


def test_tables_sharing_most_columns_may_be_renames() -> None:
    columns = "(id int, email text, name text)"

    assert renames(f"CREATE TABLE users {columns}", f"CREATE TABLE members {columns}") == [
        (RenameTable("users", "members"), 0.8)
    ]
    assert (
        renames(
            "CREATE TABLE users (id int, email text, name text)",
            "CREATE TABLE members (id int, title text, size int)",
        )
        == []
    )


def test_renames_found_in_reverse_are_the_reverse_renames() -> None:
    before = "CREATE TABLE t (id int, created date, code text, kind text)"
    after = "CREATE TABLE t (id int, created_at date, created_on date, kode text, type text)"

    forward = [rename for rename, _ in renames(before, after)]
    backward = [rename for rename, _ in renames(after, before)]

    assert len(forward) == 2
    assert backward == [
        RenameColumn(rename.table, rename.new_name, rename.column)
        for rename in forward
        if isinstance(rename, RenameColumn)
    ]


def test_detected_renames_come_first_and_the_rest_uses_new_names() -> None:
    before = schema("CREATE TABLE users (id int PRIMARY KEY, nickname text, email text, bio text)")
    after = schema(
        "CREATE TABLE app_users (id int PRIMARY KEY, nick_name text, email text NOT NULL, bio text)"
    )

    assert diff_schemas(before, after, PG, detect_renames=True) == (
        RenameTable("users", "app_users"),
        RenameColumn("app_users", "nickname", "nick_name"),
        SetNotNull("app_users", "email"),
    )
    assert len(diff_schemas(before, after, PG)) == 2


def test_renaming_a_column_follows_every_reference() -> None:
    before = schema(
        """
        CREATE TABLE users (id int PRIMARY KEY, nick text UNIQUE,
                            CONSTRAINT named CHECK (nick <> '"nick"'));
        CREATE TABLE posts (id int, author text REFERENCES users (nick));
        CREATE INDEX ix_nick ON users (lower(nick), nick) WHERE nick IS NOT NULL;
        """,
        SQLITE,
    )

    renamed = apply_renames(before, [RenameColumn("users", "NICK", "handle")], SQLITE)

    users, posts = renamed.table("users"), renamed.table("posts")
    assert users is not None
    assert posts is not None
    assert users.column_names == ("id", "handle")
    assert users.unique_constraints[0].columns == ("handle",)
    assert users.check_constraints[0].expression == Expression('"handle" <> \'"nick"\'')
    assert users.check_constraints[0].expression.columns == {"handle"}
    index = users.indexes[0]
    assert [str(element.key) for element in index.elements] == ['LOWER("handle")', "handle"]
    assert str(index.where) == 'NOT "handle" IS NULL'
    assert posts.foreign_keys[0].ref_columns == ("handle",)


def test_renaming_a_table_follows_foreign_keys() -> None:
    before = schema(
        """
        CREATE TABLE users (id int PRIMARY KEY, boss int REFERENCES users);
        CREATE TABLE posts (id int, author int REFERENCES users);
        """
    )

    renamed = apply_renames(before, [RenameTable("users", "people")], PG)

    people, posts = renamed.table("people"), renamed.table("posts")
    assert people is not None
    assert posts is not None
    assert people.foreign_keys[0].ref_table == "people"
    assert posts.foreign_keys[0].ref_table == "people"


def test_postgresql_keeps_the_names_it_derived_from_old_names() -> None:
    before = schema(
        """
        CREATE TABLE users (id int PRIMARY KEY, nick text UNIQUE CHECK (nick <> ''));
        CREATE INDEX ON users (nick);
        """
    )
    changes: list[Change] = [
        RenameTable("users", "people"),
        RenameColumn("people", "nick", "handle"),
    ]

    people = apply_renames(before, changes, PG).table("people")

    assert people is not None
    assert people.primary_key is not None
    assert people.primary_key.name == "users_pkey"
    assert [unique.name for unique in people.unique_constraints] == ["users_nick_key"]
    assert [check.name for check in people.check_constraints] == ["users_nick_check"]
    assert [index.name for index in people.indexes] == ["users_nick_idx"]


def test_sqlite_has_no_implicit_names_to_keep() -> None:
    before = schema("CREATE TABLE users (id int PRIMARY KEY, nick text UNIQUE)", SQLITE)

    people = apply_renames(before, [RenameTable("users", "people")], SQLITE).table("people")

    assert people is not None
    assert people.primary_key is not None
    assert people.primary_key.name is None


def test_renaming_a_missing_table_is_an_error() -> None:
    with pytest.raises(ValueError, match="cannot rename 'ghost'"):
        apply_renames(schema("CREATE TABLE t (a int)"), [RenameTable("ghost", "x")], PG)


RENAMES: list[Change] = [
    RenameTable("users", "people"),
    RenameColumn("people", "nick", "handle"),
    RenameColumn("posts", "body", "handle"),
]


@pytest.mark.parametrize(
    ("sql", "before"),
    [
        (
            'SELECT count(*) FROM "people" WHERE "people"."handle" IS NULL',
            'SELECT count(*) FROM "users" WHERE "users"."nick" IS NULL',
        ),
        ('SELECT \'"handle"\' FROM "people"', 'SELECT \'"handle"\' FROM "users"'),
        ('SELECT "handle" FROM "other"', 'SELECT "handle" FROM "other"'),
        ('SELECT "handle" FROM "people", "posts"', None),
    ],
    ids=["renamed", "literal", "other table", "ambiguous"],
)
def test_queries_are_rewritten_with_the_names_before_renames(sql: str, before: str | None) -> None:
    assert names_before_renames(sql, RENAMES, PG) == before
