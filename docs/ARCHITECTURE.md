# Architecture

> Work in progress: this document grows with each layer. It records the decisions that are
> not obvious from the code and the reasons behind them.

## Layers

```
cli ──► emit ──► plan ─┐
                risk ──┴─► diff ──► dialects ──► model
loaders ─────────────────────────► dialects ──► model
```

Dependencies only point downwards, and `import-linter` fails the build otherwise (see the
contracts in `pyproject.toml`). Everything below `cli` and `loaders` is pure: it neither
reads files nor talks to databases, and it never imports sqlglot, SQLAlchemy, Typer or Rich.
That keeps the diff, the risk rules and the planner testable with plain model objects.

## Model

- **Immutable.** Every object is a `frozen`, `slots` dataclass holding tuples and frozensets.
  Changes and plans can reference model objects without defensive copies, and model objects
  are hashable, which the diff uses to compare collections.
- **Canonical by construction.** Collections whose order means nothing (tables, constraints,
  indexes, enum types) are sorted in `__post_init__`, so two schemas describing the same
  database are equal (`==`) regardless of declaration order. Table columns keep their order:
  it is visible to applications and needed to emit `CREATE TABLE`.
- **Internally consistent.** Constructors reject keys and indexes on unknown columns,
  duplicate names and empty key lists, so a bug in a loader surfaces as an error at load
  time instead of as a wrong migration.
- **Values are canonical SQL.** Defaults, CHECK conditions and index expressions are stored as
  canonical SQL text (`Expression.sql`) plus the columns they read (`Expression.columns`),
  which the planner needs to know what depends on a column.

## Loaders and normalization

All normalization happens in the loaders, so the diff can compare with `==`. Both loaders
send raw SQL through the same functions in `loaders/normalize.py`:

| Source spelling                          | Canonical form        | Why                                      |
|------------------------------------------|-----------------------|------------------------------------------|
| `int`, `INTEGER`, `int4`                 | `integer`             | aliases of one type                      |
| `varchar` vs `text`                      | kept apart            | different types in PostgreSQL            |
| `numeric(10)`                            | `numeric(10,0)`       | scale defaults to 0                      |
| `timestamp(6)`                           | `timestamp`           | 6 is the default precision               |
| `float(10)` / `float(30)`                | `real` / `double precision` | SQL maps precision to storage size |
| PG `char`                                | `char(1)`             | PostgreSQL default length                |
| `int[][]`                                | `integer[]`           | PostgreSQL ignores array dimensions      |
| `'x'::text` on a `text` column           | `'x'`                 | PostgreSQL adds the cast when reporting  |
| `'-1'::integer`, `'42'` on a number      | `-1`, `42`            | the value the column actually stores     |
| `'t'`, `1` on a boolean                  | `TRUE`                | the value the column actually stores     |
| `now()`                                  | `CURRENT_TIMESTAMP`   | same function                            |
| `DEFAULT NULL`                           | no default            | same behaviour                           |
| `(Age > 0)` in PostgreSQL                | `"age" > 0`           | identifier folding; quoting everything avoids keyword lists |
| `(price > (0)::numeric)` in a PG catalog | `"price" > 0`         | PostgreSQL adds parentheses and casts to stored conditions |
| `status = ANY (ARRAY['a'::text, 'b'])`   | `"status" IN ('a', 'b')` | how PostgreSQL stores `IN` lists      |
| `nextval('s'::regclass)`                 | `NEXTVAL('s')`        | PostgreSQL resolves the name when it stores the default |
| `integer` + owned sequence `nextval`     | `serial`              | what `serial` expands to               |
| primary key column without `NOT NULL`    | `NOT NULL`            | PostgreSQL enforces it; SQLite only fails to because of a documented legacy bug |

sqlglot parses and renders SQL, through small dialect subclasses (`loaders/_sqlglot.py`)
that fix the few places where sqlglot loses schema information and that render types in
their canonical spelling.

### Parse errors are fatal, unknown objects are warnings

If a statement fails to parse, loading fails with its line and column. Skipping it would
be dangerous: a table missing from the target schema turns into `DROP TABLE` in the
migration. Statements that cannot change the schema (`SET`, `GRANT`, `INSERT`, `OWNER TO`)
are ignored, and objects outside the MVP (views, functions, sequences, exclusion
constraints) are skipped with a warning that the CLI shows.

### Live SQLite: catalog for structure, stored DDL for text-only definitions

SQLite parses the DDL itself and exposes the result through its catalog: declared types
(`pragma_table_xinfo`), nullability, defaults, key columns, referential actions
(`pragma_foreign_key_list`) and the columns of UNIQUE constraints (`pragma_index_list`).
The live loader reads this structure through SQLAlchemy, independently of dbdelta's DDL
parser, which lets `tests/integration/test_loader_equivalence.py` check the parser and the
normalization against SQLite itself.

Constraint names, CHECK conditions, index expressions, partial index predicates and the
`AUTOINCREMENT` keyword exist only as text, so they come from the DDL stored in
`sqlite_master`, parsed by the same reader as schema files. The SQLAlchemy inspector is
not used for these because, as of SQLAlchemy 2.0, it skips expression indexes, omits
partial index predicates, drops the referential actions of unnamed foreign keys and misses
UNIQUE constraints whose column names differ in case from the column declaration.

The database is opened read-only (`mode=ro`), and a missing file is an error: sqlite3 would
otherwise create an empty database, which reads as "drop every table".

### Live PostgreSQL: inspector plus catalog queries

The SQLAlchemy inspector provides columns, keys, UNIQUE and CHECK constraints, foreign keys
and enum types. The catalog is queried directly where the inspector is approximate:
`format_type` gives exact column types, `pg_get_serial_sequence` tells a `serial` column
from a column that borrows another sequence, `pg_get_indexdef` gives index definitions,
which the DDL reader parses like a schema file, and `pg_class.reltuples` gives row
estimates for the risk rules (`-1`, never analyzed, means "unknown"). Indexes that back a
primary key or UNIQUE constraint belong to the constraint and are not loaded twice.

The loader sets the search path to the loaded schema, so PostgreSQL prints names of types,
sequences and tables without a schema prefix, exactly as a schema file names them. Views,
materialized views, foreign and partitioned tables are skipped with a warning; partitions
are left out silently. Sessions run with `default_transaction_read_only=on`, so the server
itself refuses any write.

### pg_dump output

`pg_dump --schema-only` output loads like any schema file: psql meta-commands such as
`\restrict` are dropped, `CREATE SEQUENCE ... OWNED BY` plus a `nextval` default becomes a
`serial` column, `ADD GENERATED ... AS IDENTITY` is applied to its column, and names
qualified with the loaded schema lose the qualifier. Objects in other schemas are skipped.

## Diff

`diff_schemas(source, target, dialect)` returns a tuple of typed, immutable changes, one per
difference (`AddColumn`, `AlterColumnType`, `DropIndex`, ...). `Change` is a union of these
records rather than a class hierarchy, so risk rules, the planner and emitters dispatch with
`match` and mypy checks that every change type is handled.

- **Names follow the dialect.** Tables, columns and constraints are matched with
  `dialects.name_key`: exactly in PostgreSQL, case-insensitively in SQLite.
- **Constraints and indexes are paired by definition.** A name only counts when both sides
  name the object explicitly. `PRIMARY KEY (id)` in a file therefore matches `users_pkey` in a
  database, while two different explicit names are a real difference. Pairs sharing an
  explicit name are formed first, so a named constraint is never matched to an unnamed twin.
- **Changing a constraint or index is drop + add**, because neither PostgreSQL nor SQLite can
  alter their definition in place.
- **Column order** is ignored unless strict checking is requested; new columns are expected at
  the end of the table, where `ADD COLUMN` puts them.

### Renames

A diff only sees names, so a renamed column is a drop and an add, which as a migration
loses the column's data. `possible_renames` pairs a dropped column with an added column of
the same type in the same table, and a dropped table with an added table sharing at least
half of its columns (by name and type). Confidence mixes name similarity (`difflib`) with
shape: `0.6 · name + 0.4 · (same nullability, default, identity)` for columns and
`0.4 · name + 0.6 · shared columns` for tables; pairs below 0.6 are ignored, and each object
joins at most one pair. Confidence is symmetric, so the renames of a down migration are the
reverse of the up migration's.

By default a pair only produces a `possible-rename` warning. With `--detect-renames`,
`diff_schemas` turns pairs into `RenameTable` and `RenameColumn`: tables first, then the
columns of the renamed tables, then the remaining changes, which use the new names.
`apply_renames` computes the schema as it is after the renames. It follows every reference
(keys, foreign keys of other tables, index keys, CHECK conditions) and, in PostgreSQL, pins
the names PostgreSQL derived from the old names (`users_nick_key` keeps its name after
`users` becomes `members`), so later statements address the constraints the database really
has.

## Plan

`plan_migration(changes, source, dialect)` orders changes in fixed phases: renames first,
because the other changes use the new names; then remove what
depends on objects that are about to go (foreign keys, then indexes and constraints), then
drop columns and tables, then create enum types, tables and columns, alter columns, add
constraints and indexes, and add foreign keys last, when every table, column and key they
need exists. Enum types are dropped at the very end, once no column uses them.

Tables are created in foreign key order and dropped in reverse. The order comes from
`plan/graph.py`, a thin layer over the standard library's `graphlib` that makes the order
deterministic and breaks cycles by ignoring one dependency per cycle.

PostgreSQL checks foreign keys in DDL; SQLite only checks them when rows change. The
`checks_foreign_keys_in_ddl` dialect trait switches on three extra rules:

- a foreign key that closes a cycle between new tables, or references a key created later in
  the migration, is added with `ALTER TABLE` after all tables exist;
- tables that reference each other are released (their foreign key dropped) before dropping;
- a foreign key whose referenced primary key, UNIQUE constraint or unique index is replaced
  is dropped before and re-added after, because PostgreSQL refuses to drop a key in use.

In SQLite all foreign keys stay inline in `CREATE TABLE`, which is the only place SQLite
accepts them.

Where ALTER TABLE changes columns in place (PostgreSQL), CHECK constraints and indexes whose
SQL reads a column whose type changes are dropped before and re-added after: PostgreSQL would
keep them with a cast to the old type, which is not what the target declares. In SQLite, a
table that would lose every column is rebuilt, because SQLite cannot drop a table's last
column before the new ones are added.

### Down migrations

A down migration is the migration from the target back to the source: the same pipeline
with the sides swapped, so it gets its own risks (dropping the columns the up migration
added is dangerous too). What it cannot do is bring back data. `irreversible_changes` marks
every table and column it creates (the up migration dropped them with their contents) and
every type change that reverses a conversion that may have changed values (rounding,
truncating, reformatting); conversions that keep every value or fail, such as `integer` to
`bigint` or a shorter `varchar`, are reversible. Marked steps carry an `IRREVERSIBLE` comment
in the SQL and are listed in every report format.

## Risk

`assess(changes, context)` runs every registered rule over the diff and returns findings,
most dangerous first. A finding has a level (`info`, `warning`, `danger`), a plain explanation,
a safer alternative and, when the data decides whether the change succeeds, a query to run
before migrating (duplicates, NULLs, rows without a parent, values that do not fit).

- **A registry of plain functions.** A rule is a function registered with `@change_rule` (one
  change at a time) or `@rule` (the whole migration) under a stable code. Codes appear in
  reports and are what users list to silence a rule. Adding a rule is adding a function.
- **Rules look at changes, not SQL.** They read the diff and dialect facts, never the plan
  or the emitted statements, so they stay independent of how the SQL is written. The facts
  they share with the emitter, such as which PostgreSQL type changes rewrite the table, live
  in `dialects/`; `tests/integration/test_postgres_rewrites.py` checks those predictions
  against PostgreSQL by watching the table's relfilenode.
- **Levels follow what is known.** `RiskContext.row_estimates` holds table sizes when the
  source is a live database. Dropping from a table known to be empty is `info`; locks on
  tables known to be smaller than `large_table_rows` are `info`; anything unknown is treated
  as large and full.
- **Check queries are real.** `tests/integration/test_risk_checks.py` runs every suggested
  query against SQLite and PostgreSQL for every fixture pair, with and without rename
  detection. Queries run before the migration: those about columns it adds are left out,
  a foreign key to a table it creates is checked by counting the rows that need a match,
  and queries written with renamed names are translated back to the old ones.
- **Findings also appear in the SQL**, as comments above the statements they concern.

| Rule | Level | What it catches |
|------|-------|-----------------|
| `drop-table` | danger | dropping a table deletes its rows |
| `drop-column` | danger | dropping a column deletes its values |
| `enum-values` | danger / warning | removed enum values fail on rows that use them; reordering changes sorting |
| `narrowing-type` | danger | a narrower type cannot hold every value (info in SQLite, which does not enforce types) |
| `type-rewrite` | warning | the type change rewrites the table under an exclusive lock, possibly with USING |
| `add-not-null-column` | danger | NOT NULL without a default fails on a table with rows |
| `add-column-rewrite` | warning | identity columns and per-row defaults rewrite the table |
| `set-not-null` | warning | fails on NULLs and scans the table under an exclusive lock |
| `unique-duplicates` | warning | existing duplicates make a new unique key or primary key fail |
| `check-violations` | warning | existing rows may violate a new CHECK |
| `foreign-key` | warning | validation locks both tables; SQLite does not check existing rows |
| `index-lock` | warning | CREATE INDEX blocks writes without `--concurrent-indexes` |
| `sqlite-rebuild` | warning | SQLite rebuilds the table: copies all rows, drops triggers |
| `possible-rename` | warning | a dropped and an added table or column of the same shape look like a rename |
| `rename` | warning | a rename breaks code, views and functions that use the old name |

## Emit

Emitters turn a plan into a `Script`: statements grouped into blocks, each block either run
in a transaction (`BEGIN` ... `COMMIT`) or not. Every statement carries a one-line
description of its change as a comment, so the SQL reads as a reviewed change list.
Identifiers are always quoted and literals always escaped through `emit/quoting.py`; the
only SQL taken verbatim is canonical SQL that came from a schema (defaults, CHECK
conditions, index expressions).

### PostgreSQL

- The migration is one transaction, because PostgreSQL DDL is transactional.
- New enum values are added in an earlier transaction: PostgreSQL refuses to use an enum
  value in the transaction that added it.
- With `concurrent_indexes`, index builds and drops on existing tables use `CONCURRENTLY`
  outside the transaction. A unique index that a foreign key relies on stays inside, next to
  the foreign key changes that depend on it.
- A type change gets `USING` only when PostgreSQL has no assignment cast. Adding it
  everywhere would be wrong: `USING col::varchar(10)` silently truncates, while a plain type
  change fails on values that are too long.
- Unnamed constraints are dropped by the name PostgreSQL gave them, computed like
  PostgreSQL's `makeObjectName` (including truncation to 63 bytes) and checked against
  PostgreSQL 16 in the tests.
- An enum type losing or reordering values is renamed, recreated, and its columns converted
  through `text`, with their defaults dropped and restored around the conversion.
- A column that becomes an identity or serial column gets its sequence moved past the
  values already in the table.

### SQLite

SQLite's `ALTER TABLE` can only add and drop columns. The planner turns every other change
to an existing table into one `RebuildTable`, which follows the procedure in SQLite's
documentation: create the new table under a temporary name, copy the rows, drop the old
table, rename the new one, recreate the indexes. Foreign keys are switched off around the
transaction (the pragma has no effect inside one) and `PRAGMA foreign_key_check` runs before
the commit. Columns SQLite cannot add to a populated table (NOT NULL without a default,
non-constant defaults) are added by rebuilding as well.

## CLI

`cli/analysis.py` runs the pipeline once per command: resolve the dialect, load both sides,
drop the ignored tables, diff, assess, plan and emit. The commands differ only in what they
print and how they exit:

| Command | Default format | Exit code                                                       |
|---------|----------------|-----------------------------------------------------------------|
| `diff`  | `text`         | 0; 2 for invalid input                                          |
| `plan`  | `sql`          | 0; 2 for invalid input                                          |
| `check` | `text`         | 1 if a `danger` finding exists without `--allow-destructive`; 2 for invalid input |

Every format carries the same content: loader warnings, changes, findings and the SQL.
`text` is a Rich report for people, `sql` is the migration with a header comment, `json`
is for tools (findings point at changes by index), and `markdown` is meant for a pull
request comment, with the SQL folded into `<details>`.

- **stdout stays clean.** Status that the chosen output does not show on the terminal
  (loader warnings, the check verdict, where `--output` wrote to) goes to stderr, so
  `dbdelta plan a.sql b.sql > migration.sql` produces a file that is only SQL.
- **Colors only on terminals.** Rich decides from the stream (and honours `NO_COLOR` and
  `FORCE_COLOR`); files and pipes get plain text without Rich's trailing padding.
- **User data is never markup.** Names and paths enter Rich as `Text` objects and are
  escaped in Markdown, so a table called `[red]` or `a|b` prints literally. Every comment
  line in SQL starts with `--`, including lines of names that contain line breaks.
- **Configuration.** `dbdelta.toml` in the working directory (or `--config`) holds the same
  settings as the options, spelled like them. Options override it and pattern lists add to
  it. Unknown keys are errors: a typo in `ignore-tables` would otherwise turn ignored tables
  into `DROP TABLE` statements.
- **Dialects.** A URL names its dialect; files use `--dialect`, then the configuration, then
  PostgreSQL. Both sides must be the same dialect, because one migration is written.

## Testing strategy

- **Unit tests** cover normalization, the diff, the planner and each emitter.
- **Fixture pairs** in `tests/fixtures/{common,sqlite,postgres}/NN_name/` hold `a.sql`,
  `b.sql` and optionally `seed.sql`. `common` pairs use portable DDL and run on both dialects.
- **Snapshots:** the migration for each pair is compared with `expected.<dialect>.sql` next to
  it. `pytest --update-snapshots` rewrites them, and the diff shows every change in output.
- **Round-trip on SQLite:** build A in memory, insert the seed rows, run the migration, reload
  the schema and require a strict diff against B to be empty, surviving tables to keep their
  rows, `PRAGMA foreign_key_check` to pass and a second plan to be empty.
- **Round-trip on PostgreSQL:** the same round-trip for every PostgreSQL and common pair on a
  real server, each test in its own schema, once in a single transaction and once with
  concurrent indexes.
- **Down migrations:** every pair also migrates back from B to A on both databases, with its
  seed rows; tables that existed all along must keep them. Their SQL is kept as
  `expected.<dialect>.down.sql`. A pair can hold a `dbdelta.toml`, read like the CLI's,
  for settings such as `detect-renames`.
- **Property-based tests** (`tests/property/`, Hypothesis): for generated schemas, a schema
  never differs from itself, the SQL that creates it loads back into it, and rename
  detection is symmetric. Generated pairs, mostly small edits of each other, must migrate
  to the target and back on SQLite (with exact column order) and PostgreSQL. Run with
  `--hypothesis-profile=thorough` for 1000 examples instead of 100.
- **CLI:** each command runs end to end on fixture files and live databases; the text,
  JSON and Markdown reports of one pair are kept as snapshots in `tests/fixtures/cli/`.
- **Loader equivalence:** a schema file and the database built from it must load into the
  same model, on SQLite and on PostgreSQL; a `pg_dump` of each fixture must load into the
  same model as the database it was taken from.
- PostgreSQL tests need `DBDELTA_TEST_POSTGRES_URL` and are skipped without it;
  `docker compose up -d --wait` starts a suitable server. CI runs them against
  PostgreSQL 14, 16 and 18.

## Known limitations

- sqlglot cannot parse a few rarely used SQLite forms: multi-word type names such as
  `UNSIGNED BIG INT`, `ON CONFLICT` clauses, sort order inside `PRIMARY KEY (...)`, and
  `CREATE VIRTUAL TABLE` in schema files. Loading such a file fails with a parse error.
- `ALTER TABLE` with several `ALTER COLUMN` actions in one statement is skipped with a
  warning; `pg_dump` writes one action per statement.
- Not tracked (reported as warnings): collations, generated columns, SQLite `WITHOUT ROWID`
  and `STRICT`, `DEFERRABLE` and `MATCH` on foreign keys, `NULLS FIRST/LAST` in indexes.
- In SQLite, `INT PRIMARY KEY` is canonicalized like `INTEGER PRIMARY KEY`, although only
  the latter is an alias of the rowid.
- One schema is loaded per source (`public` by default in PostgreSQL, `main` in SQLite);
  references to tables in other schemas are kept qualified.
- PostgreSQL cannot reorder columns; with strict column order checking the difference is
  reported but not applied.
- Rebuilding a SQLite table with `AUTOINCREMENT` restarts its counter from the largest
  existing id rather than from the old counter.
- Index keys that are expressions are always emitted in parentheses, so an operator class
  on an expression key is not supported.
- Enum types and views are not renamed; a renamed enum type is dropped and created.
- Irreversibility is judged conservatively from types alone: a type change SQLite would
  make without touching values (it does not enforce most types) may still be marked.
