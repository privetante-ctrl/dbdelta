from pathlib import Path

import pytest

from dbdelta.cli.config import ConfigError, Settings, find_config, parse_config, read_config
from dbdelta.dialects import Dialect


def test_every_setting_is_read() -> None:
    settings = parse_config(
        {
            "dialect": "sqlite",
            "schema": "app",
            "ignore-tables": ["django_*"],
            "ignore-rules": ["index-lock"],
            "strict-column-order": True,
            "concurrent-indexes": True,
            "allow-destructive": True,
            "large-table-rows": 5000,
        }
    )

    assert settings == Settings(
        dialect=Dialect.SQLITE,
        schema="app",
        ignore_tables=("django_*",),
        ignore_rules=("index-lock",),
        strict_column_order=True,
        concurrent_indexes=True,
        allow_destructive=True,
        large_table_rows=5000,
    )


def test_an_empty_file_gives_the_defaults() -> None:
    assert parse_config({}) == Settings()


def test_unknown_settings_are_errors_with_a_suggestion() -> None:
    with pytest.raises(ConfigError, match="unknown setting 'ignore-table'; did you mean"):
        parse_config({"ignore-table": ["x"]})


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("dialect", "mysql", "dialect must be one of: postgresql, sqlite"),
        ("schema", "", "schema must be a schema name"),
        ("ignore-tables", "django_*", "ignore-tables must be a list of strings"),
        ("ignore-rules", [1], "ignore-rules must be a list of strings"),
        ("strict-column-order", "yes", "strict-column-order must be true or false"),
        ("large-table-rows", 0, "large-table-rows must be a positive integer"),
        ("large-table-rows", True, "large-table-rows must be a positive integer"),
    ],
)
def test_mistyped_settings_are_errors(key: str, value: object, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config({key: value})


def test_options_override_settings_and_add_patterns() -> None:
    configured = Settings(
        dialect=Dialect.SQLITE,
        ignore_tables=("a",),
        concurrent_indexes=True,
        large_table_rows=10,
    )

    settings = configured.override(
        ignore_tables=("b",), concurrent_indexes=False, strict_column_order=True
    )

    assert settings == Settings(
        dialect=Dialect.SQLITE,
        ignore_tables=("a", "b"),
        strict_column_order=True,
        concurrent_indexes=False,
        large_table_rows=10,
    )


def test_options_that_are_not_given_keep_the_settings() -> None:
    configured = Settings(dialect=Dialect.SQLITE, schema="app", allow_destructive=True)

    assert configured.override() == configured


def test_the_file_in_the_directory_is_found(tmp_path: Path) -> None:
    assert find_config(None, tmp_path) is None

    (tmp_path / "dbdelta.toml").write_text("", encoding="utf-8")

    assert find_config(None, tmp_path) == tmp_path / "dbdelta.toml"
    assert find_config(tmp_path / "other.toml", tmp_path) == tmp_path / "other.toml"


def test_read_config_names_the_file_in_errors(tmp_path: Path) -> None:
    path = tmp_path / "dbdelta.toml"
    path.write_text("dialect = 'oracle'\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"dbdelta\.toml: dialect must be one of"):
        read_config(path)


def test_invalid_toml_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "dbdelta.toml"
    path.write_text("dialect = \n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r"dbdelta\.toml: Invalid value"):
        read_config(path)


def test_a_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        read_config(tmp_path / "missing.toml")
