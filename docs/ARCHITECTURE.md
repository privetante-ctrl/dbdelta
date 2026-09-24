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
- Only one schema is loaded (`public` in PostgreSQL, `main` in SQLite).
