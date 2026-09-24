"""Build a normalized :mod:`dbdelta.model` schema from a DDL file or a live database.

All parsing and type/default normalization happens here, so that the layers
above compare canonical values only.
"""

from dbdelta.loaders.base import LoadError, LoadResult

__all__ = ["LoadError", "LoadResult"]
