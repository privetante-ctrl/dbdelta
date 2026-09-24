"""Result and error types shared by all loaders."""

from dataclasses import dataclass

from dbdelta.model import Schema


class LoadError(Exception):
    """A schema source cannot be read or describes an invalid schema."""


@dataclass(frozen=True, slots=True)
class LoadResult:
    """A loaded schema together with notes about what the loader skipped or ignored."""

    schema: Schema
    warnings: tuple[str, ...] = ()
