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
- 34 fixture schema pairs with expected SQL and round-trip tests on SQLite and PostgreSQL;
  loader equivalence tests between schema files, `pg_dump` output and live databases.
- Command-line interface: `dbdelta diff`, `plan` and `check` with `text`, `sql`, `json`
  and `markdown` output, `--output`, `--ignore-table`, `--ignore-rule`, `--dialect`,
  `--schema`, `--strict-column-order`, `--concurrent-indexes`, `--large-table-rows` and
  settings in `dbdelta.toml`. `check` exits with 1 on dangerous changes unless
  `--allow-destructive` is given.
- `docker-compose.yml` with a PostgreSQL server for the tests; CI covers PostgreSQL 14, 16
  and 18.
- Risk assessment with 13 rules, each with a level, an explanation, a safer alternative and,
  where the data decides, a query to run before migrating. Findings are also printed as
  comments in the generated SQL.
