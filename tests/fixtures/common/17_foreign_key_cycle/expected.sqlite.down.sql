-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- drop table employees
-- DANGER drop-table: Dropping employees permanently deletes all of its rows.
DROP TABLE "employees";

-- drop table departments
-- DANGER drop-table: Dropping departments permanently deletes all of its rows.
DROP TABLE "departments";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
