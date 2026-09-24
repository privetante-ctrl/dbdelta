"""sqlglot dialects adjusted to read schemas faithfully.

sqlglot targets transpilation, so a few of its choices lose information that matters when
comparing schemas. These subclasses correct them and render every data type in dbdelta's
canonical spelling, which keeps expressions such as ``'x'::text`` comparable across sources.
"""

from typing import ClassVar

from sqlglot import exp
from sqlglot.dialects.dialect import Dialect as SqlglotDialect
from sqlglot.dialects.postgres import Postgres
from sqlglot.dialects.sqlite import SQLite
from sqlglot.generators.postgres import PostgresGenerator
from sqlglot.generators.sqlite import SQLiteGenerator
from sqlglot.parsers.sqlite import SQLiteParser
from sqlglot.tokenizer_core import TokenType

from dbdelta.dialects import Dialect
from dbdelta.loaders.types import canonical_type

WITHOUT_ROWID = "WITHOUT ROWID"


class _PostgresGenerator(PostgresGenerator):
    def datatype_sql(self, expression: exp.DataType) -> str:
        return str(canonical_type(expression, Dialect.POSTGRESQL))


class _Postgres(Postgres):
    Generator = _PostgresGenerator


class _SQLiteParser(SQLiteParser):
    PROPERTY_PARSERS: ClassVar = {
        **SQLiteParser.PROPERTY_PARSERS,
        "WITHOUT": lambda self: self._parse_without_rowid(),
    }

    def _parse_without_rowid(self) -> exp.Property | None:
        if not self._match_text_seq("ROWID"):
            self.raise_error("Expected ROWID after WITHOUT")
            return None
        return exp.Property(this=exp.var(WITHOUT_ROWID), value=exp.true())


class _SQLiteGenerator(SQLiteGenerator):
    def datatype_sql(self, expression: exp.DataType) -> str:
        return str(canonical_type(expression, Dialect.SQLITE))


class _SQLite(SQLite):
    class Tokenizer(SQLite.Tokenizer):
        # The generic tokenizer reads INT8 as a one-byte integer; in SQLite schemas it is
        # the PostgreSQL spelling of bigint.
        KEYWORDS: ClassVar = {**SQLite.Tokenizer.KEYWORDS, "INT8": TokenType.BIGINT}

    Parser = _SQLiteParser
    Generator = _SQLiteGenerator


_DIALECTS: dict[Dialect, SqlglotDialect] = {
    Dialect.POSTGRESQL: _Postgres(),
    Dialect.SQLITE: _SQLite(),
}


def sqlglot_dialect(dialect: Dialect) -> SqlglotDialect:
    """Return the sqlglot dialect used to parse and render SQL of ``dialect``."""
    return _DIALECTS[dialect]
