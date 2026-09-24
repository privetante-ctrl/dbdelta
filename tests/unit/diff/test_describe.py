import pytest

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
    describe,
)
from dbdelta.model import (
    CheckConstraint,
    Column,
    DataType,
    EnumType,
    Expression,
    ForeignKey,
    Identity,
    Index,
    IndexElement,
    PrimaryKey,
    ReferentialAction,
    Table,
    UniqueConstraint,
)

INTEGER = DataType("integer")
MOOD = EnumType("mood", ("sad", "ok"))
FK = ForeignKey(("org_id",), "orgs", ("id",), ReferentialAction.CASCADE, name="fk_org")
INDEX = Index(
    "ix_email",
    (IndexElement(Expression('LOWER("email")')), IndexElement("id", descending=True)),
    unique=True,
    where=Expression('"id" > 0'),
    method="btree_gin",
)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (AddEnum(MOOD), "create enum type mood ('sad', 'ok')"),
        (DropEnum(MOOD), "drop enum type mood"),
        (
            AlterEnum(MOOD, EnumType("mood", ("sad", "ok", "happy"))),
            "change values of enum type mood from ('sad', 'ok') to ('sad', 'ok', 'happy')",
        ),
        (AddTable(Table("users", (Column("id", INTEGER),))), "create table users"),
        (DropTable(Table("users", (Column("id", INTEGER),))), "drop table users"),
        (
            AddColumn("users", Column("n", INTEGER, nullable=False, default="0")),
            "add column users.n integer NOT NULL DEFAULT 0",
        ),
        (
            AddColumn("users", Column("id", INTEGER, identity=Identity.ALWAYS)),
            "add column users.id integer [always]",
        ),
        (AddColumn("t", Column("anything", DataType(""))), "add column t.anything"),
        (DropColumn("users", Column("n", INTEGER)), "drop column users.n"),
        (
            AlterColumnType("users", "n", INTEGER, DataType("varchar", (20,))),
            "change type of users.n from integer to varchar(20)",
        ),
        (SetNotNull("users", "n"), "make users.n NOT NULL"),
        (DropNotNull("users", "n"), "allow NULL in users.n"),
        (SetDefault("users", "n", None, "1"), "set default of users.n to 1"),
        (DropDefault("users", "n", "1"), "drop default of users.n"),
        (
            AlterIdentity("users", "id", Identity.SERIAL, None),
            "change identity of users.id from serial to none",
        ),
        (ReorderColumns("t", ("a", "b"), ("b", "a")), "reorder columns of t to (b, a)"),
        (AddPrimaryKey("t", PrimaryKey(("a", "b"))), "add primary key on t (a, b)"),
        (DropPrimaryKey("t", PrimaryKey(("a",), "t_pk")), "drop primary key t_pk on t (a)"),
        (
            AddForeignKey("users", FK),
            "add foreign key fk_org users (org_id) -> orgs (id) ON DELETE CASCADE",
        ),
        (
            DropForeignKey(
                "users", ForeignKey(("a",), "p", ("id",), on_update=ReferentialAction.SET_NULL)
            ),
            "drop foreign key users (a) -> p (id) ON UPDATE SET NULL",
        ),
        (AddUnique("t", UniqueConstraint(("a", "b"))), "add unique constraint on t (a, b)"),
        (DropUnique("t", UniqueConstraint(("a",), "uq")), "drop unique constraint uq on t (a)"),
        (
            AddCheck("t", CheckConstraint(Expression('"a" > 0'), "positive")),
            'add check constraint positive on t ("a" > 0)',
        ),
        (
            DropCheck("t", CheckConstraint(Expression('"a" > 0'))),
            'drop check constraint on t ("a" > 0)',
        ),
        (
            AddIndex("users", INDEX),
            'create unique index ix_email on users using btree_gin (LOWER("email"), id DESC)'
            ' where "id" > 0',
        ),
        (DropIndex("t", Index(None, (IndexElement("a"),))), "drop index on t (a)"),
    ],
)
def test_describe(change: Change, expected: str) -> None:
    assert describe(change) == expected
