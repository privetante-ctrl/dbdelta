from dbdelta.dialects import Dialect
from dbdelta.diff import diff_schemas
from dbdelta.emit import emit_migration
from dbdelta.loaders import load_ddl
from dbdelta.plan import plan_migration
from dbdelta.risk import RiskContext, assess


def test_risk_findings_annotate_the_statements_they_concern() -> None:
    dialect = Dialect.SQLITE
    source = load_ddl("CREATE TABLE t (a INT, b TEXT); CREATE TABLE u (x INT)", dialect).schema
    target = load_ddl("CREATE TABLE t (a BIGINT, b TEXT)", dialect).schema
    changes = diff_schemas(source, target, dialect)
    findings = assess(changes, RiskContext(dialect, source, target))

    script = emit_migration(plan_migration(changes, source, target, dialect), findings=findings)

    comments = [statement.comment for statement in script.statements() if statement.comment]
    drop_u = next(comment for comment in comments if comment.startswith("drop table u"))
    rebuild_t = next(comment for comment in comments if comment.startswith("rebuild table t"))
    assert "DANGER drop-table: Dropping u permanently deletes" in drop_u
    assert "WARNING sqlite-rebuild: SQLite cannot make these changes to t" in rebuild_t
    assert "drop-table" not in rebuild_t
    assert all(len(line) <= 94 for comment in comments for line in comment.splitlines())
