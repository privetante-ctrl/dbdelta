# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Project skeleton: package layout, tooling and CI.
- Immutable schema model: tables, columns, primary and foreign keys, UNIQUE and CHECK
  constraints, indexes (unique, partial, expression, access method) and enum types.
- Schema loading from PostgreSQL and SQLite DDL files, and from live SQLite databases.
- Normalization of type aliases, defaults and expressions, so that equivalent schemas
  compare equal whichever source they come from.
