import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import (
    AddCheck,
    AddColumn,
    AddEnum,
    AddForeignKey,
    AddIndex,
    AddPrimaryKey,
    AddTable,
    AddUnique,
    AlterColumnType,
    AlterEnum,
    AlterIdentity,
    Change,
    DropCheck,
    DropColumn,
    DropDefault,
    DropEnum,
    DropForeignKey,
    DropIndex,
    DropNotNull,
    DropPrimaryKey,
    DropTable,
    DropUnique,
    ReorderColumns,
    SetDefault,
    SetNotNull,
    diff_schemas,
)
from dbdelta.loaders import load_ddl
from dbdelta.model import (
    Column,
    DataType,
    Expression,
    ForeignKey,
    Identity,
    Index,
    IndexElement,
    PrimaryKey,
    ReferentialAction,
    Schema,
    Table,
    UniqueConstraint,
)

PG = Dialect.POSTGRESQL
SQLITE = Dialect.SQLITE
INTEGER = DataType("integer")


def schema(ddl: str, dialect: Dialect = PG) -> Schema:
    return load_ddl(ddl, dialect).schema


def diff(before: str, after: str, dialect: Dialect = PG, **options: bool) -> tuple[Change, ...]:
    return diff_schemas(schema(before, dialect), schema(after, dialect), dialect, **options)


def test_identical_schemas_have_no_changes() -> None:
    ddl = """
        CREATE TYPE mood AS ENUM ('sad', 'ok');
        CREATE TABLE p (id int PRIMARY KEY, code text UNIQUE);
        CREATE TABLE c (id int PRIMARY KEY, p_id int REFERENCES p, m mood DEFAULT 'ok',
                        CHECK (id > 0));
        CREATE INDEX ix ON c (p_id) WHERE id > 10;
    """
    assert diff(ddl, ddl) == ()


def test_declaration_order_is_not_a_difference() -> None:
    before = """
        CREATE TABLE a (x int, y int, UNIQUE (x), CHECK (x > 0), CHECK (y > 0));
        CREATE TABLE b (z int);
        CREATE INDEX i1 ON a (x); CREATE INDEX i2 ON a (y);
    """
    after = """
        CREATE TABLE b (z int);
        CREATE TABLE a (y int, x int, CHECK (y > 0), CHECK (x > 0), UNIQUE (x));
        CREATE INDEX i2 ON a (y); CREATE INDEX i1 ON a (x);
    """
    assert diff(before, after) == ()


def test_column_order_is_checked_only_in_strict_mode() -> None:
    before, after = "CREATE TABLE t (a int, b int)", "CREATE TABLE t (b int, a int)"

    assert diff(before, after) == ()
    assert diff(before, after, strict_column_order=True) == (
        ReorderColumns("t", ("a", "b"), ("b", "a")),
    )


def test_columns_added_at_the_end_keep_strict_order() -> None:
    before, after = "CREATE TABLE t (a int, b int)", "CREATE TABLE t (a int, b int, c int)"

    assert diff(before, after, strict_column_order=True) == (AddColumn("t", Column("c", INTEGER)),)


def test_columns_added_in_the_middle_break_strict_order() -> None:
    changes = diff(
        "CREATE TABLE t (a int, b int)",
        "CREATE TABLE t (a int, c int, b int)",
        strict_column_order=True,
    )

    assert changes[-1] == ReorderColumns("t", ("a", "b"), ("a", "c", "b"))


def test_tables_added_and_dropped() -> None:
    changes = diff("CREATE TABLE old (a int)", "CREATE TABLE new (b int)")

    assert changes == (
        AddTable(Table("new", (Column("b", INTEGER),))),
        DropTable(Table("old", (Column("a", INTEGER),))),
    )


def test_columns_added_and_dropped() -> None:
    changes = diff(
        "CREATE TABLE t (a int, b text)", "CREATE TABLE t (a int, c text NOT NULL DEFAULT 'x')"
    )

    assert changes == (
        DropColumn("t", Column("b", DataType("text"))),
        AddColumn("t", Column("c", DataType("text"), nullable=False, default="'x'")),
    )


def test_column_attribute_changes() -> None:
    changes = diff(
        "CREATE TABLE t (a int, b int NOT NULL, c int DEFAULT 1, d int,"
        " e int GENERATED ALWAYS AS IDENTITY)",
        "CREATE TABLE t (a bigint NOT NULL, b int, c int, d int DEFAULT 2, e int NOT NULL)",
    )

    assert changes == (
        AlterColumnType("t", "a", INTEGER, DataType("bigint")),
        SetNotNull("t", "a"),
        DropNotNull("t", "b"),
        DropDefault("t", "c", "1"),
        SetDefault("t", "d", None, "2"),
        AlterIdentity("t", "e", Identity.ALWAYS, None),
    )


def test_changed_default_is_a_single_set_default() -> None:
    changes = diff("CREATE TABLE t (a int DEFAULT 1)", "CREATE TABLE t (a int DEFAULT 2)")

    assert changes == (SetDefault("t", "a", "1", "2"),)


def test_equivalent_spellings_are_not_differences() -> None:
    before = "CREATE TABLE t (a int4 DEFAULT '-1'::integer, b varchar(5) DEFAULT 'x'::text)"
    after = "CREATE TABLE t (a INTEGER DEFAULT -1, b character varying(5) DEFAULT 'x')"

    assert diff(before, after) == ()


def test_varchar_without_length_is_not_text() -> None:
    changes = diff("CREATE TABLE t (a varchar)", "CREATE TABLE t (a text)")

    assert changes == (AlterColumnType("t", "a", DataType("varchar"), DataType("text")),)


def test_primary_key_changes() -> None:
    assert diff("CREATE TABLE t (a int)", "CREATE TABLE t (a int PRIMARY KEY)") == (
        SetNotNull("t", "a"),
        AddPrimaryKey("t", PrimaryKey(("a",))),
    )
    assert diff(
        "CREATE TABLE t (a int, b int, PRIMARY KEY (a))",
        "CREATE TABLE t (a int, b int, PRIMARY KEY (a, b))",
    ) == (
        SetNotNull("t", "b"),
        DropPrimaryKey("t", PrimaryKey(("a",))),
        AddPrimaryKey("t", PrimaryKey(("a", "b"))),
    )


@pytest.mark.parametrize(
    ("before", "after", "changed"),
    [
        ("PRIMARY KEY (a)", "CONSTRAINT t_pkey PRIMARY KEY (a)", False),
        ("CONSTRAINT pk_one PRIMARY KEY (a)", "CONSTRAINT pk_two PRIMARY KEY (a)", True),
        ("UNIQUE (a)", "CONSTRAINT t_a_key UNIQUE (a)", False),
        ("CONSTRAINT uq_one UNIQUE (a)", "CONSTRAINT uq_two UNIQUE (a)", True),
        ("CHECK (a > 0)", "CONSTRAINT t_a_check CHECK (a > 0)", False),
        ("CONSTRAINT one CHECK (a > 0)", "CONSTRAINT two CHECK (a > 0)", True),
        ("FOREIGN KEY (a) REFERENCES p", "CONSTRAINT t_a_fkey FOREIGN KEY (a) REFERENCES p", False),
        (
            "CONSTRAINT fk_one FOREIGN KEY (a) REFERENCES p",
            "CONSTRAINT fk_two FOREIGN KEY (a) REFERENCES p",
            True,
        ),
    ],
)
def test_constraint_names_only_count_when_both_sides_name_them(
    before: str, after: str, changed: bool
) -> None:
    template = "CREATE TABLE p (id int PRIMARY KEY); CREATE TABLE t (a int NOT NULL, {})"

    changes = diff(template.format(before), template.format(after))

    assert (len(changes) == 2) is changed


def test_same_named_constraint_is_paired_before_an_unnamed_twin() -> None:
    before = Table(
        "t",
        (Column("a", INTEGER),),
        unique_constraints=(UniqueConstraint(("a",), "uq"), UniqueConstraint(("a",))),
    )
    after = Table(
        "t", (Column("a", INTEGER),), unique_constraints=(UniqueConstraint(("a",), "uq"),)
    )

    assert diff_schemas(Schema((before,)), Schema((after,)), PG) == (
        DropUnique("t", UniqueConstraint(("a",))),
    )


def test_foreign_key_changes_are_drop_and_add() -> None:
    template = "CREATE TABLE p (id int PRIMARY KEY); CREATE TABLE t (a int REFERENCES p {})"

    changes = diff(template.format(""), template.format("ON DELETE CASCADE"))

    assert changes == (
        DropForeignKey("t", ForeignKey(("a",), "p", ("id",))),
        AddForeignKey("t", ForeignKey(("a",), "p", ("id",), ReferentialAction.CASCADE)),
    )


def test_unique_and_check_changes() -> None:
    changes = diff(
        "CREATE TABLE t (a int, b int, UNIQUE (a), CHECK (a > 0))",
        "CREATE TABLE t (a int, b int, UNIQUE (a, b), CHECK (a >= 0))",
    )

    assert [type(change) for change in changes] == [DropUnique, AddUnique, DropCheck, AddCheck]


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("CREATE INDEX ix ON t (a)", "CREATE INDEX ix ON t (a)", []),
        ("CREATE INDEX ON t (a)", "CREATE INDEX t_a_idx ON t (a)", []),
        ("CREATE INDEX ix ON t (a)", "CREATE INDEX ix ON t (b)", [DropIndex, AddIndex]),
        ("CREATE INDEX ix ON t (a, b)", "CREATE INDEX ix ON t (b, a)", [DropIndex, AddIndex]),
        ("CREATE INDEX ix ON t (a)", "CREATE INDEX ix ON t (a DESC)", [DropIndex, AddIndex]),
        ("CREATE INDEX ix ON t (a)", "CREATE UNIQUE INDEX ix ON t (a)", [DropIndex, AddIndex]),
        ("CREATE INDEX ix ON t (a)", "CREATE INDEX ix ON t (a) WHERE b > 0", [DropIndex, AddIndex]),
        ("CREATE INDEX ix ON t (a)", "CREATE INDEX ix ON t USING hash (a)", [DropIndex, AddIndex]),
        ("CREATE INDEX ix ON t (a)", "CREATE INDEX ix ON t USING btree (a)", []),
        ("CREATE INDEX one ON t (a)", "CREATE INDEX two ON t (a)", [DropIndex, AddIndex]),
        ("", "CREATE INDEX ix ON t (lower(c))", [AddIndex]),
    ],
)
def test_index_changes(before: str, after: str, expected: list[type]) -> None:
    table = "CREATE TABLE t (a int, b int, c text);"

    changes = diff(table + before, table + after)

    assert [type(change) for change in changes] == expected


def test_enum_changes() -> None:
    changes = diff(
        "CREATE TYPE a AS ENUM ('x'); CREATE TYPE b AS ENUM ('x', 'y')",
        "CREATE TYPE b AS ENUM ('x', 'y', 'z'); CREATE TYPE c AS ENUM ('x')",
    )

    assert [type(change) for change in changes] == [DropEnum, AlterEnum, AddEnum]


def test_sqlite_compares_names_case_insensitively() -> None:
    before = """
        CREATE TABLE Users (ID INTEGER PRIMARY KEY, Email TEXT, UNIQUE (EMAIL));
        CREATE INDEX IX ON Users (Email);
    """
    after = """
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, UNIQUE (email));
        CREATE INDEX ix ON users (email);
    """
    assert diff(before, after, SQLITE) == ()


def test_postgresql_compares_quoted_names_exactly() -> None:
    changes = diff('CREATE TABLE "Users" (a int)', "CREATE TABLE users (a int)")

    assert [type(change) for change in changes] == [DropTable, AddTable]


def test_changes_inside_a_table_use_the_source_name() -> None:
    changes = diff("CREATE TABLE Users (Email TEXT)", "CREATE TABLE users (email INT)", SQLITE)

    assert changes == (AlterColumnType("Users", "Email", DataType("text"), INTEGER),)


def test_diff_is_the_mirror_image_of_the_reverse_diff() -> None:
    before = "CREATE TABLE t (a int); CREATE INDEX ix ON t (a)"
    after = "CREATE TABLE t (a int, b text); CREATE TABLE u (x int)"

    forward = diff(before, after)
    backward = diff(after, before)

    assert {type(change).__name__ for change in forward} == {"AddColumn", "AddTable", "DropIndex"}
    assert {type(change).__name__ for change in backward} == {
        "DropColumn",
        "DropTable",
        "AddIndex",
    }


def test_expression_index_keys_are_compared_by_sql() -> None:
    def schema_with(key: str) -> Schema:
        index = Index("ix", (IndexElement(Expression(key, frozenset({"a"}))),))
        return Schema((Table("t", (Column("a", INTEGER),), indexes=(index,)),))

    assert diff_schemas(schema_with('LOWER("a")'), schema_with('LOWER("a")'), PG) == ()
    assert [
        type(change)
        for change in diff_schemas(schema_with('LOWER("a")'), schema_with('UPPER("a")'), PG)
    ] == [DropIndex, AddIndex]
