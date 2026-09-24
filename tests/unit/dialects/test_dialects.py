import pytest

from dbdelta.dialects import Dialect, ascii_lower, name_key


def test_ascii_lower_leaves_non_ascii_letters_alone() -> None:
    assert ascii_lower("ÉtéUSERS") == "Étéusers"


@pytest.mark.parametrize(
    ("dialect", "same"),
    [(Dialect.POSTGRESQL, False), (Dialect.SQLITE, True)],
)
def test_name_key_follows_the_dialect_case_rules(dialect: Dialect, same: bool) -> None:
    assert (name_key("Users", dialect) == name_key("users", dialect)) is same


def test_only_postgresql_checks_foreign_keys_in_ddl() -> None:
    assert Dialect.POSTGRESQL.traits.checks_foreign_keys_in_ddl
    assert not Dialect.SQLITE.traits.checks_foreign_keys_in_ddl
