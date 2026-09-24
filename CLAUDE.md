# dbdelta: project rules

`dbdelta` compares two database schema states (source A = current, target B = desired)
and generates a safe up/down migration script with warnings about dangerous operations.
Each side is either a `.sql` DDL file or a live database URL (`postgresql://…`, `sqlite:///…`).
Pipeline: load → normalize → diff → assess risk → plan (order) → emit SQL.

MVP dialects: PostgreSQL 14+ and SQLite. MySQL/MSSQL must be addable without touching the core.
MVP objects: tables, columns, PK, FK (ON DELETE/UPDATE), UNIQUE, CHECK, indexes (unique,
partial, PG index method), PG ENUM types. Out of scope (do not implement, do not block):
views, functions, triggers, sequences, partitioning, grants.

## Commands

```bash
uv sync --all-extras              # install everything, incl. the postgres extra
uv run pytest                     # tests (add --cov for coverage)
uv run ruff check --fix && uv run ruff format
uv run mypy                       # strict, over src/ and tests/
uv run lint-imports               # architecture contracts
uv run pre-commit run --all-files # all of the above
```

## Architecture

`src/dbdelta/`, dependencies point strictly downwards (enforced by import-linter in pyproject):

| Layer       | Responsibility                                                          | May import                        |
|-------------|-------------------------------------------------------------------------|-----------------------------------|
| `cli/`      | Typer commands, config (`dbdelta.toml`), output formats, side effects   | everything                        |
| `emit/`     | Per-dialect SQL generators behind a common `Emitter` interface          | plan, risk, diff, dialects, model |
| `plan/`     | Ordering, dependency resolution, transaction blocks                     | diff, dialects, model             |
| `risk/`     | Risk rules, one class/function per rule, registered in a registry       | diff, dialects, model             |
| `diff/`     | `Schema × Schema → list[Change]` with typed changes                     | dialects, model                   |
| `loaders/`  | DDL file (sqlglot) and live DB (SQLAlchemy) → model, all normalization  | dialects, model                   |
| `dialects/` | Facts about each dialect (the `Dialect` enum, later its capabilities)   | model                             |
| `model/`    | Frozen dataclasses: Schema, Table, Column, PrimaryKey, ForeignKey, …    | nothing                           |

- `model`, `dialects`, `diff`, `risk`, `plan`, `emit` never import sqlglot, SQLAlchemy, Typer or Rich.
- I/O (files, databases, terminal) happens only in `loaders/` and `cli/`. Everything else is pure.
- No speculative abstractions. The only planned extension points are dialects and risk rules.

## Domain rules that must not regress

- **Normalization** happens in loaders so the diff compares canonical values:
  `int`/`integer`/`int4` are one type; `varchar` without length ≠ `text`; `'x'::text` = `'x'`
  in defaults; index column order matters; table column order is ignored unless
  `--strict-column-order`; names of unnamed constraints are never a difference.
- **Loaders fail loudly**: a statement that does not parse is an error, never a warning (a
  missing `CREATE TABLE` would become a `DROP TABLE`). Objects outside the MVP are skipped with
  a warning in `LoadResult.warnings`. Live databases are opened read-only.
- **Ordering**: create tables in FK-topological order, drop in reverse; cyclic FKs are added
  with separate `ALTER TABLE` after the tables exist; drop dependent indexes/constraints
  before dropping a column/table.
- **Renames are never silent**: drop+add with a compatible shape is reported as a possible
  rename with a confidence score; only `--detect-renames` turns it into a RENAME.
- **Every risk** has a level (`info`/`warning`/`danger`), a plain explanation and a safer
  alternative.
- **Down migrations** are best-effort; data-losing reversals are marked `IRREVERSIBLE`
  in the SQL (comment) and in the report.
- **Transactions**: wrap in `BEGIN`/`COMMIT` where DDL is transactional; statements that cannot
  run in a transaction (`CREATE INDEX CONCURRENTLY`) go into a separate block.
- **SQLite** cannot alter columns: generate a table rebuild (create new, copy, drop, rename,
  recreate indexes) and flag it in the report.
- **SQL safety**: always quote identifiers and literals through the emitter helpers;
  never build SQL by concatenating raw values.

## Code style

- English everywhere: code, docstrings, docs, commit messages, CLI output.
- Python 3.11+, full type hints, `mypy --strict` clean, `ruff` clean.
- Comments explain *why*, never *what*. No separator comments (`# ----`, `# ====`).
- Model objects are `@dataclass(frozen=True, slots=True)`; use tuples/frozensets, not lists/dicts.

## Testing

- Unit tests for normalization, diff, every risk rule and ordering; snapshot tests of emitted SQL.
- Round-trip is the main correctness guarantee: load A into a real DB, apply the plan, reflect
  back, assert it equals B, then assert `diff(result, B)` is empty.
- Property-based tests (hypothesis): `diff(S, S)` is empty; generated schemas round-trip.
- Fixture pairs live in `tests/fixtures/{common,postgres,sqlite}/<NN_name>/{a.sql,b.sql}`;
  `common` pairs use portable DDL and run on every dialect.
- `tests/integration/test_loader_equivalence.py`: a DDL file and the database built from it
  must load into the same model. Add a case whenever normalization changes.
- PostgreSQL tests are marked `@pytest.mark.postgres` and use `DBDELTA_TEST_POSTGRES_URL`.
- Coverage of `diff/`, `risk/`, `plan/` stays at or above 90 %.

## Workflow

- Conventional Commits (`feat(diff): …`, `fix(emit): …`, `test: …`), small and focused.
- Work proceeds in phases; after each phase stop, summarize what was done and how to run it,
  and wait for the maintainer's go-ahead.
