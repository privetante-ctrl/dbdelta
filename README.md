# dbdelta

Compare two database schemas and generate a safe migration script, with
warnings about dangerous operations.

> **Status:** early development. The full documentation will land together
> with the first usable release.

## Usage

```bash
dbdelta diff  current.sql desired.sql          # report the changes and their risks
dbdelta plan  current.sql desired.sql -o migration.sql
dbdelta check postgresql://app@db/app desired.sql --format markdown  # for CI
dbdelta plan  current.sql desired.sql --down   # roll back; marks IRREVERSIBLE steps
```

Each side is a `.sql` file or a database URL (`postgresql://…`, `sqlite:///…`); files are
read as PostgreSQL unless `--dialect sqlite` is given. `check` exits with 1 when a change is
dangerous, such as dropping a column, unless `--allow-destructive` is given. A dropped and
an added column that look alike are reported as a possible rename; `--detect-renames`
turns them into `RENAME COLUMN`. Settings can
live in `dbdelta.toml`:

```toml
dialect = "postgresql"
ignore-tables = ["django_*"]
ignore-rules = ["index-lock"]
concurrent-indexes = true
detect-renames = true
```

## Development

```bash
uv sync --all-extras
uv run pre-commit install
uv run pytest
```
