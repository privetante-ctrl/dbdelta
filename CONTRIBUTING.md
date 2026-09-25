# Contributing to dbdelta

Thanks for helping. This guide covers the setup, the checks a change must pass, and the two
places dbdelta is meant to grow: risk rules and dialects. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
explains how the pieces fit together and why.

## Setup

```bash
uv sync --all-extras          # Python 3.11+, all dependencies including the postgres extra
uv run pre-commit install     # run the checks below before every commit
```

PostgreSQL tests need a server. Docker Compose starts one with settings made for tests:

```bash
docker compose up -d --wait
export DBDELTA_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres
POSTGRES_VERSION=14 docker compose up -d --wait   # another version, when a change depends on it
```

Without `DBDELTA_TEST_POSTGRES_URL`, tests marked `postgres` are skipped.

## Checks

```bash
uv run pytest                     # all tests; --cov for coverage
uv run pre-commit run --all-files # ruff, ruff format, mypy --strict, import contracts, ...
uv run pytest tests/property --hypothesis-profile=thorough   # 1000 examples per property
```

CI runs the same on Python 3.11, 3.12 and 3.13 against PostgreSQL 14, 16 and 18, and
requires at least 90 % coverage of `diff/`, `risk/` and `plan/`.

- **Snapshots.** Expected SQL lives next to each fixture pair (`expected.<dialect>.sql` and
  `.down.sql`), and the example outputs in `examples/shop/output/`. After a change to what
  dbdelta prints, run `uv run pytest --update-snapshots` and read the diff before
  committing: it is the review of your change's effect.
- **Fixture pairs.** A new kind of change deserves a pair in
  `tests/fixtures/{common,postgres,sqlite}/NN_name/` with `a.sql`, `b.sql` and, when rows
  matter, `seed.sql`. `common` pairs use portable DDL and run on every dialect. Every pair is
  round-tripped against real databases in both directions.
- **Normalization.** When a loader learns a new spelling, add a case to
  `tests/integration/test_loader_equivalence.py`, which requires a file and the database
  built from it to load into the same model.
- **Layers.** `lint-imports` enforces that dependencies point downwards and that the core
  (`model` to `emit`) never imports sqlglot, SQLAlchemy, Typer or Rich.

## Style

- English everywhere, including CLI output and commit messages.
- Full type hints, `mypy --strict` and `ruff` clean.
- Comments explain why, not what.
- Model objects are frozen, slotted dataclasses of tuples and frozensets.
- SQL is built from quoted identifiers and escaped literals (`dialects/quoting.py`), never by
  pasting raw values.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat(risk): …`, `fix(emit): …`, `test: …`), each small and passing on its own.

## Adding a risk rule

A rule is a function that looks at changes and returns findings. Say dropping an index
deserves a note, because queries that used it may become slow:

1. **Write the rule** in the module of `src/dbdelta/risk/rules/` that fits its topic (a new
   module must be imported in `risk/rules/__init__.py`). `@change_rule` gives it one change
   at a time; use `@rule` when it needs all of them at once.

   ```python
   @change_rule("drop-index", "Dropping an index can slow down the queries that used it.")
   def drop_index(change: Change, context: RiskContext) -> Finding | None:
       if not isinstance(change, DropIndex) or context.is_empty(change.table):
           return None
       name = change.index.name or "an unnamed index"
       return Finding(
           "drop-index",
           Level.INFO,
           f"index {name} on {change.table}",
           f"Queries that used {name} fall back to scanning {change.table}.",
           "Check the query plans of the queries on this table before dropping the index.",
           (change,),
       )
   ```

   The code (`drop-index`) is permanent: users see it in reports and list it in
   `ignore-rules`. Pick the level by consequence: `danger` loses data or fails on existing
   data, `warning` locks or may fail, `info` is worth knowing. Every finding explains what
   can go wrong and offers a safer way, both as full sentences.

2. **Offer a check query** (`check_sql`) when the data decides whether the change works.
   It runs *before* the migration: never read a column the migration adds
   (`columns_exist` in `rules/_helpers.py` tells), and quote every name with
   `quote_identifier`.

3. **Test it** in `tests/unit/risk/test_rules.py`: the finding it gives, and at least one
   case where it must stay silent. Add a change that triggers it to
   `test_every_rule_is_exercised_and_explains_itself`.

4. **Document it** in the rule tables of `README.md` and `docs/ARCHITECTURE.md`, and
   regenerate the snapshots: findings appear as comments in the expected SQL.

## Adding a dialect

MySQL or SQL Server can be added without changing the diff, the rules or the planner. The
work, using MySQL as the example:

1. **Facts** (`src/dbdelta/dialects/`)
   - Add the member to `Dialect`. Its value is the SQLAlchemy URL scheme (`mysql`).
   - Add its `DialectTraits` to `_TRAITS`: whether names are case-sensitive, whether DDL
     checks foreign keys, whether ALTER TABLE can change columns and constraints, and
     whether DDL is transactional (in MySQL it is not). The planner and the rules read
     these instead of checking for a dialect by name.
   - Put the dialect's own facts (default constraint names, which type changes rewrite the
     table) in `dialects/mysql.py`.
2. **Loading** (`src/dbdelta/loaders/`)
   - Map the dialect to a sqlglot dialect in `_sqlglot.py`, and teach `types.py` its type
     aliases, default schema and identifier folding.
   - Write the live loader (`loaders/mysql.py`) on the SQLAlchemy inspector, reading from
     the catalog what the inspector reports approximately. Open connections read-only.
   - Register the URL scheme and the engine in `database.py`.
3. **Writing SQL** (`src/dbdelta/emit/`)
   - Subclass `Emitter` in `emit/mysql.py`: type spelling, column definitions, index names
     and `_emit`, which groups statements into blocks. Register it in `emit/__init__.py`.
4. **Risk rules**: most rules apply as they are. Where locking or behaviour differs, branch
   on `context.dialect` and word the finding for that database.
5. **Tests**
   - Add a fixture group `tests/fixtures/mysql/` and list the dialect for `common` pairs in
     `tests/support/fixtures.py`; generate the expected SQL with `--update-snapshots`.
   - Add a live-database fixture and round-trip tests like `test_roundtrip_postgres.py`,
     loader equivalence cases, and a service in CI and `docker-compose.yml`.
6. **Docs**: the dialect list and limitations in `README.md`, and its section in
   `docs/ARCHITECTURE.md`.

## Pull requests

Describe what changes for users, include the snapshot diffs that show it, and make sure
`pre-commit` and the tests pass. A bug fix comes with the test that failed before it.
