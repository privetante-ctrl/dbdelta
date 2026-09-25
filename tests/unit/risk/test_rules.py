from typing import Any

import pytest

from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.loaders import load_ddl
from dbdelta.risk import Finding, Level, RiskContext, assess, registered_rules

PG = Dialect.POSTGRESQL
SQLITE = Dialect.SQLITE


def findings(
    before: str,
    after: str,
    dialect: Dialect = PG,
    *,
    detect_renames: bool = False,
    **context: Any,
) -> list[Finding]:
    source = load_ddl(before, dialect).schema
    target = load_ddl(after, dialect).schema
    changes = diff_schemas(source, target, dialect, detect_renames=detect_renames)
    return list(assess(changes, RiskContext(dialect, source, target, **context)))


def found(before: str, after: str, dialect: Dialect = PG, **context: Any) -> set[tuple[str, Level]]:
    return {
        (finding.rule, finding.level) for finding in findings(before, after, dialect, **context)
    }


def only(before: str, after: str, rule: str, dialect: Dialect = PG, **context: Any) -> Finding:
    matching = [
        finding for finding in findings(before, after, dialect, **context) if finding.rule == rule
    ]
    assert len(matching) == 1, matching
    return matching[0]


TABLE = "CREATE TABLE t (id int PRIMARY KEY, a int, b text);"


class TestDataLoss:
    def test_dropping_a_table_is_dangerous(self) -> None:
        finding = only(TABLE, "", "drop-table")

        assert finding.level is Level.DANGER
        assert finding.check_sql == 'SELECT count(*) FROM "t"'

    def test_dropping_an_empty_table_is_informational(self) -> None:
        assert only(TABLE, "", "drop-table", row_estimates={"t": 0}).level is Level.INFO

    def test_known_row_counts_are_mentioned(self) -> None:
        finding = only(TABLE, "", "drop-table", row_estimates={"t": 12345})

        assert "(about 12,345 rows)" in finding.message

    def test_dropping_a_column_is_dangerous(self) -> None:
        finding = only(TABLE, "CREATE TABLE t (id int PRIMARY KEY, a int)", "drop-column")

        assert finding.level is Level.DANGER
        assert finding.subject == "t.b"
        assert finding.check_sql == 'SELECT count(*) FROM "t" WHERE "t"."b" IS NOT NULL'

    def test_dropping_a_column_of_an_empty_table_is_informational(self) -> None:
        after = "CREATE TABLE t (id int PRIMARY KEY, a int)"

        assert only(TABLE, after, "drop-column", row_estimates={"t": 0}).level is Level.INFO


class TestEnumValues:
    BEFORE = "CREATE TYPE mood AS ENUM ('sad', 'meh', 'ok'); CREATE TABLE t (m mood, h mood[])"

    def test_removing_values_is_dangerous(self) -> None:
        after = "CREATE TYPE mood AS ENUM ('sad', 'ok'); CREATE TABLE t (m mood, h mood[])"

        finding = only(self.BEFORE, after, "enum-values")

        assert finding.level is Level.DANGER
        assert finding.message.startswith("Value 'meh' is removed from mood")
        assert finding.check_sql == (
            'SELECT count(*) FROM "t" WHERE "t"."m"::text IN (\'meh\');\n'
            'SELECT count(*) FROM "t" WHERE "t"."h"::text[] && ARRAY[\'meh\']'
        )

    def test_reordering_values_is_a_warning(self) -> None:
        after = "CREATE TYPE mood AS ENUM ('ok', 'meh', 'sad'); CREATE TABLE t (m mood, h mood[])"

        assert only(self.BEFORE, after, "enum-values").level is Level.WARNING

    def test_adding_values_is_safe(self) -> None:
        after = (
            "CREATE TYPE mood AS ENUM ('sad', 'meh', 'fine', 'ok', 'great');"
            "CREATE TABLE t (m mood, h mood[])"
        )

        assert found(self.BEFORE, after) == set()


class TestTypes:
    @pytest.mark.parametrize(
        ("old", "new", "expected"),
        [
            (
                "varchar(255)",
                "varchar(50)",
                {("narrowing-type", Level.DANGER), ("type-rewrite", Level.WARNING)},
            ),
            (
                "bigint",
                "integer",
                {("narrowing-type", Level.DANGER), ("type-rewrite", Level.WARNING)},
            ),
            ("integer", "bigint", {("type-rewrite", Level.WARNING)}),
            ("varchar(10)", "varchar(20)", set()),
            ("varchar(10)", "text", set()),
            ("numeric(10,2)", "numeric(12,2)", set()),
            ("text", "integer", {("type-rewrite", Level.WARNING)}),
        ],
    )
    def test_postgresql_type_changes(self, old: str, new: str, expected: set[Any]) -> None:
        assert found(f"CREATE TABLE t (a {old})", f"CREATE TABLE t (a {new})") == expected

    def test_narrowing_explains_the_consequence_and_offers_a_check(self) -> None:
        finding = only(
            "CREATE TABLE t (a varchar(255))", "CREATE TABLE t (a varchar(50))", "narrowing-type"
        )

        assert "longer than 50 characters" in finding.message
        assert finding.check_sql == 'SELECT count(*) FROM "t" WHERE length("t"."a") > 50'

    @pytest.mark.parametrize(
        ("new", "check"),
        [
            ("smallint", '"t"."a" NOT BETWEEN -32768 AND 32767'),
            ("numeric(5,2)", 'abs("t"."a") >= 1e3'),
            ("timestamp(0)", None),
        ],
    )
    def test_narrowing_checks(self, new: str, check: str | None) -> None:
        old = "numeric(10,2)" if new.startswith("numeric") else "bigint"
        if new.startswith("timestamp"):
            old = "timestamp"

        finding = only(f"CREATE TABLE t (a {old})", f"CREATE TABLE t (a {new})", "narrowing-type")

        expected = f'SELECT count(*) FROM "t" WHERE {check}' if check else None
        assert finding.check_sql == expected

    def test_explicit_casts_are_explained(self) -> None:
        finding = only("CREATE TABLE t (a text)", "CREATE TABLE t (a integer)", "type-rewrite")

        assert "converted with USING" in finding.message

    def test_rewrites_of_small_tables_are_informational(self) -> None:
        finding = only(
            "CREATE TABLE t (a int)",
            "CREATE TABLE t (a bigint)",
            "type-rewrite",
            row_estimates={"t": 10},
        )

        assert finding.level is Level.INFO

    def test_sqlite_does_not_enforce_narrower_types(self) -> None:
        assert found(
            "CREATE TABLE t (a VARCHAR(255))", "CREATE TABLE t (a VARCHAR(50))", SQLITE
        ) == {("narrowing-type", Level.INFO), ("sqlite-rebuild", Level.WARNING)}


class TestColumns:
    def test_adding_a_not_null_column_without_default_is_dangerous(self) -> None:
        finding = only(TABLE, TABLE[:-2] + ", c int NOT NULL);", "add-not-null-column")

        assert finding.level is Level.DANGER
        assert "ADD COLUMN with a constant DEFAULT is instant" in finding.recommendation

    @pytest.mark.parametrize("column", ["c int", "c int NOT NULL DEFAULT 0"])
    def test_safe_new_columns(self, column: str) -> None:
        assert found(TABLE, TABLE[:-2] + f", {column});") == set()

    def test_adding_a_not_null_column_to_an_empty_table_is_informational(self) -> None:
        after = TABLE[:-2] + ", c int NOT NULL);"

        assert only(TABLE, after, "add-not-null-column", row_estimates={"t": 0}).level is Level.INFO

    @pytest.mark.parametrize(
        "column", ["token uuid DEFAULT gen_random_uuid()", "n int GENERATED ALWAYS AS IDENTITY"]
    )
    def test_columns_computed_per_row_rewrite_the_table(self, column: str) -> None:
        assert only(TABLE, TABLE[:-2] + f", {column});", "add-column-rewrite").level is (
            Level.WARNING
        )

    def test_set_not_null(self) -> None:
        after = "CREATE TABLE t (id int PRIMARY KEY, a int NOT NULL, b text)"

        finding = only(TABLE, after, "set-not-null")

        assert finding.level is Level.WARNING
        assert "NOT VALID" in finding.recommendation
        assert finding.check_sql == 'SELECT count(*) FROM "t" WHERE "t"."a" IS NULL'
        assert found(TABLE, after, row_estimates={"t": 0}) == set()

    def test_set_not_null_in_sqlite(self) -> None:
        before = "CREATE TABLE t (id INTEGER PRIMARY KEY, a INT)"
        after = "CREATE TABLE t (id INTEGER PRIMARY KEY, a INT NOT NULL)"

        finding = only(before, after, "set-not-null", SQLITE)

        assert finding.recommendation == "Backfill the NULLs before migrating."


class TestConstraints:
    def test_new_unique_constraints_may_meet_duplicates(self) -> None:
        after = "CREATE TABLE t (id int PRIMARY KEY, a int, b text, UNIQUE (a, b))"

        finding = only(TABLE, after, "unique-duplicates")

        assert finding.subject == "unique constraint on t (a, b)"
        assert "USING INDEX" in finding.recommendation
        assert finding.check_sql == (
            'SELECT "a", "b", count(*) FROM "t" WHERE "a" IS NOT NULL AND "b" IS NOT NULL '
            'GROUP BY "a", "b" HAVING count(*) > 1'
        )

    def test_partial_expression_unique_indexes_check_what_they_index(self) -> None:
        after = TABLE + "CREATE UNIQUE INDEX ux ON t (lower(b)) WHERE a > 0"

        finding = only(TABLE, after, "unique-duplicates")

        assert finding.check_sql == (
            'SELECT LOWER("b"), count(*) FROM "t" WHERE LOWER("b") IS NOT NULL AND ("a" > 0) '
            'GROUP BY LOWER("b") HAVING count(*) > 1'
        )

    def test_new_primary_keys_may_meet_duplicates(self) -> None:
        before = "CREATE TABLE t (a int NOT NULL)"

        assert only(before, "CREATE TABLE t (a int PRIMARY KEY)", "unique-duplicates").subject == (
            "primary key on t (a)"
        )

    def test_keys_of_new_or_empty_tables_are_safe(self) -> None:
        after = TABLE + "CREATE TABLE u (a int UNIQUE, CHECK (a > 0))"

        assert found(TABLE, after) == set()
        assert found(TABLE, TABLE[:-2] + ", UNIQUE (a));", row_estimates={"t": 0}) == set()

    def test_new_check_constraints_may_be_violated(self) -> None:
        after = "CREATE TABLE t (id int PRIMARY KEY, a int, b text, CHECK (a > 0))"

        finding = only(TABLE, after, "check-violations")

        assert finding.check_sql == 'SELECT count(*) FROM "t" WHERE NOT ("a" > 0)'
        assert "NOT VALID" in finding.recommendation

    def test_constraints_on_new_columns_have_no_check_query(self) -> None:
        before = "CREATE TABLE p (id int PRIMARY KEY); CREATE TABLE t (a int)"
        after = (
            "CREATE TABLE p (id int PRIMARY KEY);"
            "CREATE TABLE t (a int, b int UNIQUE REFERENCES p CHECK (b > 0))"
        )

        checks = {finding.rule: finding.check_sql for finding in findings(before, after)}

        assert checks == {"check-violations": None, "foreign-key": None}

    def test_unique_keys_on_new_columns_with_a_default_can_collide(self) -> None:
        before = "CREATE TABLE t (a int)"
        after = "CREATE TABLE t (a int, b int DEFAULT 0, UNIQUE (b))"

        finding = only(before, after, "unique-duplicates")

        assert finding.check_sql is None

    def test_sqlite_constraint_checks(self) -> None:
        before = "CREATE TABLE t (a INT)"
        after = "CREATE TABLE t (a INT UNIQUE CHECK (a > 0))"

        by_rule = {finding.rule: finding for finding in findings(before, after, SQLITE)}

        assert by_rule["unique-duplicates"].recommendation == "Remove the duplicates first."
        assert by_rule["check-violations"].recommendation == "Fix the violating rows first."

    def test_foreign_keys_lock_both_tables(self) -> None:
        before = "CREATE TABLE p (id int PRIMARY KEY, x int); CREATE TABLE c (p1 int, p2 int)"
        after = (
            "CREATE TABLE p (id int, x int, PRIMARY KEY (id, x));"
            "CREATE TABLE c (p1 int, p2 int, FOREIGN KEY (p1, p2) REFERENCES p (id, x))"
        )

        finding = only(before, after, "foreign-key")

        assert finding.level is Level.WARNING
        assert finding.check_sql == (
            'SELECT count(*) FROM "c" AS child WHERE child."p1" IS NOT NULL AND child."p2" IS NOT '
            'NULL AND NOT EXISTS (SELECT 1 FROM "p" AS parent WHERE parent."id" = child."p1" AND '
            'parent."x" = child."p2")'
        )

    def test_foreign_keys_in_sqlite_are_not_checked(self) -> None:
        before = "CREATE TABLE p (id INTEGER PRIMARY KEY); CREATE TABLE c (p INT)"
        after = "CREATE TABLE p (id INTEGER PRIMARY KEY); CREATE TABLE c (p INT REFERENCES p)"

        finding = only(before, after, "foreign-key", SQLITE)

        assert "PRAGMA foreign_key_check" in finding.message


class TestIndexes:
    AFTER = TABLE + "CREATE INDEX ix ON t (a)"

    def test_index_builds_block_writes(self) -> None:
        finding = only(TABLE, self.AFTER, "index-lock")

        assert finding.level is Level.WARNING
        assert "--concurrent-indexes" in finding.recommendation

    def test_small_tables_are_informational(self) -> None:
        assert only(TABLE, self.AFTER, "index-lock", row_estimates={"t": 99}).level is Level.INFO

    def test_concurrent_builds_are_safe(self) -> None:
        assert found(TABLE, self.AFTER, concurrent_indexes=True) == set()

    def test_indexes_backing_foreign_keys_stay_in_the_transaction(self) -> None:
        after = TABLE + "CREATE UNIQUE INDEX ux ON t (b); CREATE TABLE r (b text REFERENCES t (b))"

        finding = only(TABLE, after, "index-lock", concurrent_indexes=True)

        assert "a foreign key depends on it" in finding.recommendation

    def test_sqlite_has_no_index_locking_rule(self) -> None:
        assert found(TABLE, self.AFTER, SQLITE) == set()


class TestSQLiteRebuild:
    def test_rebuilds_are_reported_with_their_changes(self) -> None:
        after = "CREATE TABLE t (id int PRIMARY KEY, a bigint NOT NULL, b text)"

        finding = only(TABLE, after, "sqlite-rebuild", SQLITE)

        assert finding.level is Level.WARNING
        assert "triggers on the table are dropped" in finding.message
        assert len(finding.changes) == 2

    def test_changes_made_in_place_need_no_rebuild(self) -> None:
        after = "CREATE TABLE t (id int PRIMARY KEY, a int, c text); CREATE INDEX ix ON t (a)"

        assert "sqlite-rebuild" not in {rule for rule, _ in found(TABLE, after, SQLITE)}

    def test_postgresql_never_rebuilds(self) -> None:
        after = "CREATE TABLE t (id int PRIMARY KEY, a bigint, b text)"

        assert "sqlite-rebuild" not in {rule for rule, _ in found(TABLE, after)}


class TestRenames:
    BEFORE = "CREATE TABLE users (id int PRIMARY KEY, nickname text, email text);"
    AFTER = "CREATE TABLE users (id int PRIMARY KEY, nick_name text, email text);"

    def test_a_drop_and_add_of_the_same_shape_may_be_a_rename(self) -> None:
        finding = only(self.BEFORE, self.AFTER, "possible-rename")

        assert finding.level is Level.WARNING
        assert finding.subject == "column users.nickname"
        assert "looks like a rename (confidence 96%)" in finding.message
        assert [type(change).__name__ for change in finding.changes] == [
            "DropColumn",
            "AddColumn",
        ]

    @pytest.mark.parametrize(
        "after",
        [
            "CREATE TABLE users (id int PRIMARY KEY, nick_name int, email text);",
            "CREATE TABLE users (id int PRIMARY KEY, phone text, email text);",
        ],
        ids=["other type", "unrelated name"],
    )
    def test_unlike_columns_are_not_renames(self, after: str) -> None:
        assert "possible-rename" not in {rule for rule, _ in found(self.BEFORE, after)}

    def test_a_table_with_the_same_columns_may_be_a_rename(self) -> None:
        after = self.BEFORE.replace("users", "accounts")

        finding = only(self.BEFORE, after, "possible-rename")

        assert finding.subject == "table users"
        assert "confidence 72%" in finding.message
        assert "deletes all of its rows" in finding.message

    def test_detected_renames_warn_about_the_old_name_only(self) -> None:
        before = self.BEFORE.replace("email text", "email text, bio text")
        after = self.AFTER.replace("users", "app_users").replace(
            "email text", "email text, bio text"
        )

        assert found(before, after, detect_renames=True) == {("rename", Level.WARNING)}
        assert [
            finding.message
            for finding in findings(before, after, detect_renames=True)
            if finding.subject.startswith("column")
        ] == [
            "Renaming column app_users.nickname to nick_name keeps its data, but application "
            "code, views, functions and triggers that still use the old name fail. The "
            "database updates keys, indexes and foreign keys itself."
        ]

    def test_unrelated_tables_are_not_renames(self) -> None:
        after = "CREATE TABLE accounts (id int PRIMARY KEY, name text, email text);"

        assert "possible-rename" not in {rule for rule, _ in found(self.BEFORE, after)}

    def test_rules_after_a_rename_know_the_table_by_its_new_name(self) -> None:
        after = "CREATE TABLE app_users (id int PRIMARY KEY, nickname text);"

        dropped = only(
            self.BEFORE, after, "drop-column", detect_renames=True, row_estimates={"users": 0}
        )

        assert dropped.subject == "app_users.email"
        assert dropped.level is Level.INFO


def test_every_rule_is_exercised_and_explains_itself() -> None:
    before = """
        CREATE TYPE mood AS ENUM ('sad', 'meh', 'ok');
        CREATE TABLE users (id int PRIMARY KEY, email varchar(255), bio text, age int, m mood);
        CREATE TABLE orders (id int PRIMARY KEY, user_id int);
        CREATE TABLE gone (id int);
    """
    after = """
        CREATE TYPE mood AS ENUM ('ok', 'sad');
        CREATE TABLE users (id int PRIMARY KEY, email varchar(50) NOT NULL UNIQUE,
                            age bigint CHECK (age > 0), m mood,
                            token uuid DEFAULT gen_random_uuid(), nick text NOT NULL);
        CREATE TABLE orders (id int PRIMARY KEY, user_id int REFERENCES users);
        CREATE INDEX ix_orders_user ON orders (user_id);
    """
    everything = (
        findings(before, after)
        + findings("CREATE TABLE t (a INT)", "CREATE TABLE t (a TEXT)", SQLITE)
        + findings(TestRenames.BEFORE, TestRenames.AFTER)
        + findings(TestRenames.BEFORE, TestRenames.AFTER, detect_renames=True)
    )

    assert {finding.rule for finding in everything} == {rule.code for rule in registered_rules()}
    for finding in everything:
        assert finding.message.endswith(".")
        assert finding.recommendation.endswith(".")
