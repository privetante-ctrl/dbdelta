# dbdelta

Compare two database schemas and generate a safe migration script, with
warnings about dangerous operations.

> **Status:** early development. The full documentation will land together
> with the first usable release.

## Development

```bash
uv sync --all-extras
uv run pre-commit install
uv run pytest
```
