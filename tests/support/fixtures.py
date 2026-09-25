"""Discovery of the schema pairs in ``tests/fixtures``.

Each pair is a directory with ``a.sql`` (the current schema), ``b.sql`` (the desired schema)
and optionally ``seed.sql`` (rows inserted into A before migrating) and ``dbdelta.toml``
(settings such as ``detect-renames``, read like the CLI reads them). Pairs under ``common``
use portable DDL and run on every dialect; ``sqlite`` and ``postgres`` pairs on one each.
The expected migrations for a dialect are stored next to the pair as
``expected.<dialect>.sql`` and ``expected.<dialect>.down.sql``.
"""

from dataclasses import dataclass
from pathlib import Path

from dbdelta.cli.config import CONFIG_FILE, Settings, read_config
from dbdelta.dialects import Dialect

FIXTURES = Path(__file__).parent.parent / "fixtures"

_GROUPS = {
    "common": (Dialect.POSTGRESQL, Dialect.SQLITE),
    "postgres": (Dialect.POSTGRESQL,),
    "sqlite": (Dialect.SQLITE,),
}


@dataclass(frozen=True)
class FixturePair:
    path: Path

    @property
    def id(self) -> str:
        return f"{self.path.parent.name}/{self.path.name}"

    @property
    def a(self) -> str:
        return (self.path / "a.sql").read_text(encoding="utf-8")

    @property
    def b(self) -> str:
        return (self.path / "b.sql").read_text(encoding="utf-8")

    @property
    def seed(self) -> str | None:
        seed = self.path / "seed.sql"
        return seed.read_text(encoding="utf-8") if seed.exists() else None

    @property
    def settings(self) -> Settings:
        config = self.path / CONFIG_FILE
        return read_config(config) if config.exists() else Settings()

    def expected(self, dialect: Dialect, *, down: bool = False) -> Path:
        return self.path / f"expected.{dialect}{'.down' if down else ''}.sql"


def fixture_pairs(dialect: Dialect) -> list[FixturePair]:
    """All pairs that apply to ``dialect``, sorted by group and name."""
    return [
        FixturePair(path)
        for group, dialects in sorted(_GROUPS.items())
        if dialect in dialects
        for path in sorted((FIXTURES / group).iterdir())
        if path.is_dir()
    ]
