"""Quoting of identifiers and literals.

Every name and value that reaches generated SQL goes through these functions; nothing is
concatenated into SQL unquoted.
"""


def quote_identifier(name: str) -> str:
    """Quote a name so the database takes it verbatim, whatever its case or characters."""
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Quote a string literal.

    Assumes standard-conforming strings, the default since PostgreSQL 9.1 and the only mode
    of SQLite, in which a backslash has no special meaning.
    """
    return "'" + value.replace("'", "''") + "'"


def quote_qualified(name: str) -> str:
    """Quote a possibly schema-qualified name such as ``audit.log``."""
    return ".".join(quote_identifier(part) for part in name.split("."))
