"""A migration script: SQL statements grouped into transactional and plain blocks."""

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Statement:
    """One SQL statement, without its terminating semicolon.

    ``comment`` is printed on the lines above the statement. A statement with empty ``sql``
    is a note for the reader and executes nothing.
    """

    sql: str
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class Block:
    """Statements that run together, inside one transaction when ``transactional``."""

    statements: tuple[Statement, ...]
    transactional: bool
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class Script:
    """The SQL of a migration, ready to be rendered or executed."""

    blocks: tuple[Block, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not any(statement.sql for statement in self.statements())

    def statements(self) -> Iterator[Statement]:
        """Every statement, in execution order, without transaction control."""
        for block in self.blocks:
            yield from block.statements

    def render(self) -> str:
        """Render the script as SQL text, with BEGIN and COMMIT around transactional blocks."""
        sections = [_render_block(block) for block in self.blocks if block.statements]
        return "\n\n".join(sections) + "\n" if sections else ""


def _render_block(block: Block) -> str:
    header = _comment_lines(block.comment) if block.comment else []
    if block.transactional:
        header.append("BEGIN;")
    paragraphs = ["\n".join(header)] if header else []
    for statement in block.statements:
        lines = _comment_lines(statement.comment) if statement.comment else []
        if statement.sql:
            lines.append(f"{statement.sql};")
        paragraphs.append("\n".join(lines))
    if block.transactional:
        paragraphs.append("COMMIT;")
    return "\n\n".join(paragraphs)


def _comment_lines(text: str) -> list[str]:
    return [f"-- {line}" if line else "--" for line in text.splitlines()]
