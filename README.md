# dbdelta

[![CI](https://github.com/privetante-ctrl/dbdelta/actions/workflows/ci.yml/badge.svg)](https://github.com/privetante-ctrl/dbdelta/actions/workflows/ci.yml)
![Python 3.11 | 3.12 | 3.13](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![PostgreSQL 14+ | SQLite](https://img.shields.io/badge/databases-PostgreSQL%2014%2B%20%7C%20SQLite-336791)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Compare two database schemas, get the migration between them, and learn what will hurt
before you run it.**

dbdelta reads the schema you have and the schema you want, each from a `.sql` file or a live
PostgreSQL or SQLite database, and writes the migration in both directions: ordered,
transactional SQL for PostgreSQL 14+ or SQLite. Every dangerous step comes with a plain
explanation, a safer way to do it and, where the data decides, a query to run first.

<!-- Demo: record docs/demo.gif with `vhs docs/demo.tape` (https://github.com/charmbracelet/vhs). -->
<p align="center">
  <img src="docs/demo.gif" alt="dbdelta diff, plan and check in a terminal" width="820">
</p>

## Why

Schema diff tools and ORM autogenerators answer "what SQL turns A into B?". The questions
that matter in review are different: will `SET NOT NULL` lock the table while it scans every
row, will shortening a column fail on existing values, is that "renamed" column really a drop
that deletes its data, and can this be rolled back? dbdelta answers those, in a terminal, in
a pull request comment or as a CI gate.

## Features

- **Sources:** `.sql` files (including `pg_dump --schema-only` output), live PostgreSQL and
  live SQLite databases, which are opened read-only.
- **Objects:** tables, columns, primary keys, foreign keys with `ON DELETE`/`ON UPDATE`,
  UNIQUE and CHECK constraints, indexes (unique, partial, expression, PostgreSQL access
  method), identity and serial columns, PostgreSQL enum types.
- **No false differences:** `int`, `integer` and `int4` are one type, `'x'::text` equals
  `'x'`, unnamed constraints match whatever name the database gave them, and column order
  only counts when you ask. A schema file and the database built from it compare equal.
- **Correct order:** tables are created in foreign key order and dropped in reverse, cyclic
  foreign keys are added afterwards, and dependents go before what they depend on.
- **15 risk rules** with levels (`info`, `warning`, `danger`), explanations, safer
  alternatives and check queries; findings appear in the report and as comments in the SQL.
- **Renames are never silent:** a dropped and an added column or table that look alike are
  reported as a possible rename with a confidence score; `--detect-renames` turns them into
  `RENAME`, which keeps the data.
- **Down migrations:** `--down` writes the way back and marks `IRREVERSIBLE` the steps that
  cannot restore data.
- **PostgreSQL:** one transaction, new enum values committed first, `USING` only where there
  is no automatic cast, `CREATE INDEX CONCURRENTLY` in its own block on request.
- **SQLite:** changes `ALTER TABLE` cannot make become the table rebuild SQLite documents,
  keeping the rows and checking foreign keys.
- **Output** as a terminal report, SQL, JSON or Markdown for pull request comments, with exit
  codes for CI.

## Installation

dbdelta needs Python 3.11 or newer. The `postgres` extra installs the driver for live
PostgreSQL databases.

```bash
uv tool install "dbdelta[postgres] @ git+https://github.com/privetante-ctrl/dbdelta"
# or
pipx install "dbdelta[postgres] @ git+https://github.com/privetante-ctrl/dbdelta"
```

Or run it in Docker, with the current directory mounted:

```bash
docker build -t dbdelta https://github.com/privetante-ctrl/dbdelta.git
docker run --rm -v "$PWD:/work" dbdelta diff current.sql desired.sql
```

## Quick start

The [`examples/shop`](examples/shop) schemas describe a release that shortens a column, adds
a NOT NULL column, drops one, renames another and adds constraints and indexes.

```bash
cd examples/shop
dbdelta diff current.sql desired.sql
```

```text
current.sql -> desired.sql (postgresql)

Changes
 #   Change                                                                                  Risk
────────────────────────────────────────────────────────────────────────────────────────────────────
 1   change values of enum type order_status from ('new', 'paid', 'shipped') to ('new',
     'paid', 'shipped', 'refunded')
 2   drop column customers.phone                                                             danger
 3   add column customers.loyalty_tier text NOT NULL                                         danger
 4   change type of customers.email from varchar(255) to varchar(120)                        danger
 5   create unique index ux_customers_email on customers (LOWER("email"))                    warning
 ...
 9   drop column orders.created                                                              danger
10   add column orders.created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP             warning
11   create index ix_orders_customer on orders (customer_id)                                 warning

Risks

DANGER  narrowing-type  customers.email
  customers.email changes from varchar(255) to the narrower varchar(120). Values longer than 120
  characters make the migration fail.
  Safer: Check the data with the query below and clean up values that do not fit, or keep the wider
  type.
  Check before migrating:
    SELECT count(*) FROM "customers" WHERE length("customers"."email") > 120

DANGER  add-not-null-column  customers.loyalty_tier
  customers.loyalty_tier is added as NOT NULL without a default, which fails as soon as customers
  holds any row: existing rows would have no value.
  Safer: Add the column as nullable or with a DEFAULT, fill it for existing rows, then make it NOT
  NULL in a later step. In PostgreSQL 11 and later, ADD COLUMN with a constant DEFAULT is instant.
  ...

WARNING  possible-rename  column orders.created
  Column orders.created is dropped and created_at is added with the same shape; this looks like a
  rename (confidence 89%). As written, the migration deletes its values instead of keeping them.
  Safer: If it is a rename, run with --detect-renames to generate a RENAME, which keeps the data.
  Otherwise, make sure the data is no longer needed.
  ...

11 changes, 11 risks: 4 danger, 7 warning.
```

`plan` writes the SQL, with each statement's risks above it
([full output](examples/shop/output/migration.sql)):

```bash
dbdelta plan current.sql desired.sql --detect-renames --concurrent-indexes -o migration.sql
```

```sql
BEGIN;

-- rename column orders.created to created_at
-- WARNING rename: Renaming column orders.created to created_at keeps its data, but application
--   code, views, functions and triggers that still use the old name fail. The database updates
--   keys, indexes and foreign keys itself.
ALTER TABLE "orders" RENAME COLUMN "created" TO "created_at";
...
-- change type of customers.email from varchar(255) to varchar(120)
-- DANGER narrowing-type: customers.email changes from varchar(255) to the narrower varchar(120).
--   Values longer than 120 characters make the migration fail.
-- WARNING type-rewrite: Changing customers.email from varchar(255) to varchar(120) makes
--   PostgreSQL rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock
--   that blocks reads and writes.
ALTER TABLE "customers" ALTER COLUMN "email" TYPE varchar(120);
...
COMMIT;

-- CONCURRENTLY cannot run inside a transaction. If a statement fails, drop the INVALID
-- index it leaves behind before running it again.
...
-- create index ix_orders_customer on orders (customer_id)
CREATE INDEX CONCURRENTLY "ix_orders_customer" ON "orders" ("customer_id");
```

`--down` writes the way back ([full output](examples/shop/output/down.sql)); restoring a
column does not restore its values, and the SQL says so:

```sql
-- add column customers.phone text
-- IRREVERSIBLE: The up migration dropped customers.phone with its values; this adds it again
--   with every value NULL.
ALTER TABLE "customers" ADD COLUMN "phone" text;
```

## Usage

```text
dbdelta diff  SOURCE TARGET   report the changes and their risks
dbdelta plan  SOURCE TARGET   print the migration SQL
dbdelta check SOURCE TARGET   like diff, but exit with 1 on dangerous changes (for CI)
```

`SOURCE` is the current schema and `TARGET` the desired one. Each is a path to a `.sql` file
or a database URL: `postgresql://user:password@host/db` or `sqlite:///path/to/app.db`.

| Option | Meaning |
|--------|---------|
| `-f, --format text\|sql\|json\|markdown` | Output format; `diff` and `check` default to `text`, `plan` to `sql` |
| `-o, --output FILE` | Write the output to a file instead of stdout |
| `-d, --dialect postgresql\|sqlite` | Dialect of `.sql` files (default `postgresql`); URLs name their own |
| `--schema NAME` | PostgreSQL schema to compare (default `public`) |
| `--down` | Migrate back from `TARGET` to `SOURCE`, marking `IRREVERSIBLE` steps |
| `--detect-renames` | Generate `RENAME` for tables and columns that look renamed |
| `--concurrent-indexes` | Build and drop PostgreSQL indexes `CONCURRENTLY`, outside the transaction |
| `--ignore-table PATTERN` | Leave out tables matching a shell-style pattern; repeatable |
| `--ignore-rule CODE` | Skip a risk rule; repeatable |
| `--strict-column-order` | Treat a different column order as a change |
| `--large-table-rows ROWS` | Size from which lock warnings apply, when a live source tells it |
| `--allow-destructive` | Let `check` pass despite dangerous changes |
| `-c, --config FILE` | Settings file (default `dbdelta.toml` in the working directory) |

**Exit codes:** `0` success, `1` when `check` finds dangerous changes that are not allowed,
`2` for invalid options, configuration or sources (a file that does not parse, a database
that cannot be reached).

**Output streams:** stdout carries only the report or SQL, so `dbdelta plan a.sql b.sql >
migration.sql` gives a clean file. Warnings about skipped objects, the verdict of `check`
and where `--output` wrote go to stderr. Colors appear only on a terminal and follow
`NO_COLOR` and `FORCE_COLOR`.

**Configuration:** `dbdelta.toml` holds the same settings, spelled like the options; the
command line overrides it. [`examples/dbdelta.toml`](examples/dbdelta.toml) lists them all.

```toml
dialect = "postgresql"
ignore-tables = ["django_*", "schema_migrations"]
detect-renames = true
concurrent-indexes = true
```

### In CI

`dbdelta check --format markdown` produces a pull request comment with the changes, the
risks and the SQL folded away, and fails the job on dangerous changes.
[`examples/github-actions/schema-check.yml`](examples/github-actions/schema-check.yml) is a
ready workflow; [`examples/shop/output/check.md`](examples/shop/output/check.md) shows the
comment.

## Risk rules

| Rule | Level | What it catches | Safer way |
|------|-------|-----------------|-----------|
| `drop-table` | danger | Dropping a table deletes its rows | Back up, stop using it, drop in a later release |
| `drop-column` | danger | Dropping a column deletes its values | Expand and contract: stop using it first |
| `narrowing-type` | danger | A shorter varchar, smaller integer or lower precision fails or rounds | Check the data, clean up or keep the wider type |
| `add-not-null-column` | danger | NOT NULL without a default fails on a table with rows | Add nullable or with a default, backfill, then SET NOT NULL |
| `enum-values` | danger / warning | Removed enum values fail on rows using them; reordering changes sorting | Migrate the rows first |
| `type-rewrite` | warning | The type change rewrites the table under an exclusive lock, maybe with `USING` | New column, backfill, switch over |
| `add-column-rewrite` | warning | Identity columns and per-row defaults rewrite the table | Add without the default, backfill in batches |
| `set-not-null` | warning | Fails on NULLs and scans the table under an exclusive lock | `CHECK ... NOT VALID`, validate, then SET NOT NULL |
| `unique-duplicates` | warning | Existing duplicates make a new unique key fail | Remove duplicates; build the index concurrently |
| `check-violations` | warning | Existing rows may violate a new CHECK | Fix rows; add `NOT VALID` and validate separately |
| `foreign-key` | warning | Validation locks both tables; rows without a parent fail | Add `NOT VALID`, then `VALIDATE CONSTRAINT` |
| `index-lock` | warning | `CREATE INDEX` blocks writes until it is built | `--concurrent-indexes` |
| `sqlite-rebuild` | warning | SQLite copies the whole table and drops its triggers | Back up, run while idle, recreate triggers |
| `possible-rename` | warning | A dropped and an added object look like a rename | `--detect-renames` if it is one |
| `rename` | warning | Code, views and functions using the old name break | Deploy code that accepts both names first |

Rules that depend on table size (`index-lock`, lock warnings) turn into `info` when a live
database shows the table is small, and drops of empty tables are `info`.

## How it works

```
 schema A ─┐                    ┌─► risk ──────┐
 (file/DB) ├─► load & normalize ┼─► diff ──────┼─► plan ─► emit ─► SQL + report
 schema B ─┘                    └──────────────┘
```

Both sides are loaded into one immutable model, with every spelling folded into a canonical
form; the diff compares plain values into typed changes; risk rules assess the changes; the
planner orders them by dependency; an emitter writes them for the dialect.
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains the design and the reasons behind it.

Correctness is tested against real databases: each of the 35 fixture pairs is migrated from
A to B and back to A, with rows in its tables, in SQLite, in PostgreSQL 14, 16 and 18, or in
both, and property-based tests do the same for generated schemas.

## Limitations

- **Objects outside tables:** views, functions, triggers, standalone sequences, partitioned
  tables and grants are skipped with a warning, not compared.
- **One schema per source:** PostgreSQL compares one schema (`public` by default); references
  to other schemas are kept as they are.
- **Column order in PostgreSQL:** PostgreSQL cannot reorder columns, so a new column goes last
  and a different order is only reported.
- **Renames are a heuristic:** a column renamed and changed in type, or a table renamed and
  mostly rewritten, looks like a drop and an add. Enum types are never renamed.
- **Down migrations are best-effort:** they restore structure, never deleted data, and judge
  type conversions conservatively.
- **Not tracked:** collations, generated columns, `DEFERRABLE` and `MATCH` on foreign keys,
  `NULLS FIRST/LAST` in indexes, SQLite `WITHOUT ROWID` and `STRICT`. Where they appear,
  dbdelta warns.
- **Parsing:** a few rare SQLite forms are not understood by sqlglot, such as multi-word type
  names like `UNSIGNED BIG INT`; such files fail to load with a parse error.

## Roadmap

- MySQL and SQL Server dialects ([how to add one](CONTRIBUTING.md#adding-a-dialect))
- Generating `NOT VALID` foreign keys and CHECKs with a separate `VALIDATE` step, instead of
  only recommending it
- `lock_timeout` and `statement_timeout` settings in the generated PostgreSQL script
- Views and functions, ordered with the tables they depend on
- A published package on PyPI and a ready GitHub Action

## Development

```bash
uv sync --all-extras
docker compose up -d --wait
export DBDELTA_TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/postgres
uv run pytest
uv run pre-commit run --all-files
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, adding risk rules and adding
dialects, and [CHANGELOG.md](CHANGELOG.md) for what changed.

## License

[MIT](LICENSE)
