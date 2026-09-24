"""Result and error types shared by all loaders."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from dbdelta.model import Schema


class LoadError(Exception):
    """A schema source cannot be read or describes an invalid schema."""


@dataclass(frozen=True, slots=True)
class LoadResult:
    """A loaded schema together with notes about what the loader skipped or ignored.

    ``row_estimates`` maps table names to approximate row counts when the source can tell;
    risk rules use them to judge how long locks last and whether data can be lost.
    """

    schema: Schema
    warnings: tuple[str, ...] = ()
    row_estimates: Mapping[str, int] = field(default_factory=dict)
