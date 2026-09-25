# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project skeleton: package layout, tooling and CI.
- Immutable schema model: tables, columns, primary and foreign keys, UNIQUE and CHECK
  constraints, indexes (unique, partial, expression, access method) and enum types.
- Schema loading from PostgreSQL and SQLite DDL files, `pg_dump --schema-only` output, and
  live PostgreSQL and SQLite databases, opened read-only. Live PostgreSQL also provides
  row estimates for risk assessment.
- Normalization of type aliases, defaults and expressions, so that equivalent schemas
  compare equal whichever source they come from.
- Schema diff producing typed changes for enum types, tables, columns, keys, constraints
  and indexes; unnamed constraints never count as differences.
- Migration planner that orders changes by dependency, creates tables in foreign key order
  and handles foreign key cycles.
- SQL emitters for PostgreSQL and SQLite: transaction blocks, `USING` only where needed,
  concurrent index builds, enum value additions and replacements, identity columns, and
  SQLite table rebuilds that keep the data.
- 35 fixture schema pairs with expected SQL in both directions and round-trip tests on SQLite and PostgreSQL;
  loader equivalence tests between schema files, `pg_dump` output and live databases.
- Command-line interface: `dbdelta diff`, `plan` and `check` with `text`, `sql`, `json`
  and `markdown` output, `--output`, `--ignore-table`, `--ignore-rule`, `--dialect`,
  `--schema`, `--strict-column-order`, `--concurrent-indexes`, `--large-table-rows` and
  settings in `dbdelta.toml`. `check` exits with 1 on dangerous changes unless
  `--allow-destructive` is given.
- Rename detection: a dropped and an added table or column of the same shape is reported as
  a possible rename with a confidence score; `--detect-renames` generates `RENAME` instead.
- Down migrations with `--down`: the migration back from the target, with the steps that
  cannot restore lost data marked `IRREVERSIBLE` in the SQL and in every report.
- Property-based tests with Hypothesis over generated schemas and schema pairs.
- Documentation: README with real example output, `docs/ARCHITECTURE.md` with the key design
  decisions, `CONTRIBUTING.md` on adding risk rules and dialects, and `examples/` with a
  schema pair, an annotated `dbdelta.toml` and a GitHub Actions workflow that comments on pull
  requests.
- `Dockerfile` running dbdelta as a non-root user, and CI jobs that build the image and the
  wheel, require 90 % coverage of the diff, risk and plan layers, and run the property tests
  with 1000 examples weekly.
- `docker-compose.yml` with a PostgreSQL server for the tests; CI covers PostgreSQL 14, 16
  and 18.
- Risk assessment with 15 rules, each with a level, an explanation, a safer alternative and,
  where the data decides, a query to run before migrating. Findings are also printed as
  comments in the generated SQL.

### Fixed

- Turning a `serial` column into an identity column left its sequence behind, and the next
  insert could fail with a duplicate key.
- Check queries could reference a table the migration creates.
- SQLite migrations that replace every column of a table failed.
- PostgreSQL CHECK constraints and indexes on a column whose type changes kept a cast to the
  old type.
- `DEFAULT -1` on non-`integer` numeric columns loaded differently from a live PostgreSQL
  database.
- The `sqlite-rebuild` rule did not report a table rebuilt because every column is replaced.
