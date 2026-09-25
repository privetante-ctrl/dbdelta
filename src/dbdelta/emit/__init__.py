"""Render a migration plan as SQL for a specific dialect."""

from collections.abc import Sequence

from dbdelta.dialects import Dialect
from dbdelta.emit.base import EmitOptions, Emitter
from dbdelta.emit.postgresql import PostgresEmitter
from dbdelta.emit.script import Block, Script, Statement
from dbdelta.emit.sqlite import SQLiteEmitter
from dbdelta.plan import MigrationPlan
from dbdelta.risk import Finding, Irreversible

__all__ = [
    "Block",
    "EmitOptions",
    "Emitter",
    "Script",
    "Statement",
    "emit_migration",
    "emitter_for",
]

_EMITTERS: dict[Dialect, Emitter] = {
    Dialect.POSTGRESQL: PostgresEmitter(),
    Dialect.SQLITE: SQLiteEmitter(),
}


def emitter_for(dialect: Dialect) -> Emitter:
    """Return the emitter that writes SQL for ``dialect``."""
    return _EMITTERS[dialect]


def emit_migration(
    plan: MigrationPlan,
    options: EmitOptions | None = None,
    findings: Sequence[Finding] = (),
    irreversible: Sequence[Irreversible] = (),
) -> Script:
    """Write the SQL for ``plan`` in the plan's dialect, with notes as comments.

    ``findings`` are risks; ``irreversible`` marks the steps of a down migration that
    cannot restore lost data.
    """
    return emitter_for(plan.dialect).emit(plan, options, findings, irreversible)
