# Examples

## `shop/`: a release with risky changes

`current.sql` is the schema of a small shop as it runs today and `desired.sql` the one the
next release expects. The release shortens a column, adds a NOT NULL column without a
default, drops a column, renames `orders.created`, adds a CHECK, a foreign key action and
two indexes, and extends an enum.

The `output/` directory holds what dbdelta prints for them; a test keeps it current.

| File | Command |
|------|---------|
| [`output/diff.txt`](shop/output/diff.txt) | `dbdelta diff current.sql desired.sql` |
| [`output/migration.sql`](shop/output/migration.sql) | `dbdelta plan current.sql desired.sql --detect-renames --concurrent-indexes` |
| [`output/down.sql`](shop/output/down.sql) | `dbdelta plan current.sql desired.sql --detect-renames --down` |
| [`output/check.md`](shop/output/check.md) | `dbdelta check current.sql desired.sql --detect-renames --format markdown` |

Run them from `examples/shop/`. `dbdelta check` exits with 1 here, because four changes
are dangerous.

## `dbdelta.toml`

Every setting, with what it does. Copy it next to where you run dbdelta.

## `github-actions/schema-check.yml`

A workflow that runs `dbdelta check` on pull requests that change the schema and posts the
Markdown report as a comment.
