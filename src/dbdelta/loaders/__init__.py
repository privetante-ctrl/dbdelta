"""Build a normalized :mod:`dbdelta.model` schema from a DDL file or a live database.

All parsing and type/default normalization happens here, so that the layers
above compare canonical values only.
"""

from pathlib import Path

from dbdelta.dialects import Dialect
from dbdelta.loaders.base import LoadError, LoadResult
from dbdelta.loaders.database import dialect_from_url, is_url, load_database
from dbdelta.loaders.ddl import load_ddl, load_ddl_file

__all__ = [
    "LoadError",
    "LoadResult",
    "dialect_from_url",
    "is_url",
    "load_database",
    "load_ddl",
    "load_ddl_file",
    "load_source",
]


def load_source(source: str, dialect: Dialect | None = None) -> LoadResult:
    """Load a schema from a database URL or from the path of a ``.sql`` file.

    A URL determines its own dialect; ``dialect`` is then only checked against it.
    A file needs ``dialect`` because the same DDL can mean different things per database.
    """
    if is_url(source):
        url_dialect = dialect_from_url(source)
        if dialect is not None and dialect is not url_dialect:
            raise LoadError(f"{source} is a {url_dialect} database, not {dialect}")
        return load_database(source)
    if dialect is None:
        raise LoadError(f"cannot tell which SQL dialect {source} is written in")
    return load_ddl_file(Path(source), dialect)
