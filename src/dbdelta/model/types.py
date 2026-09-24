"""Canonical representation of column data types."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DataType:
    """A column type in canonical form.

    Loaders map every dialect alias onto a single canonical ``name`` (``INT``, ``int4`` and
    ``integer`` all become ``integer``) and drop parameters that only restate the default, so
    two types are interchangeable exactly when they compare equal.

    An empty ``name`` stands for a SQLite column declared without any type.
    """

    name: str
    params: tuple[int, ...] = ()
    is_array: bool = False

    def __post_init__(self) -> None:
        if not self.name and (self.params or self.is_array):
            raise ValueError("an untyped column cannot have type parameters or be an array")

    def __str__(self) -> str:
        text = self.name
        if self.params:
            text += "(" + ",".join(str(param) for param in self.params) + ")"
        if self.is_array:
            text += "[]"
        return text
