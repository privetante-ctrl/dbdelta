-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- drop table a_invoices
-- DANGER drop-table: Dropping a_invoices permanently deletes all of its rows.
DROP TABLE "a_invoices";

-- drop table b_customers
-- DANGER drop-table: Dropping b_customers permanently deletes all of its rows.
DROP TABLE "b_customers";

-- drop table c_regions
-- DANGER drop-table: Dropping c_regions permanently deletes all of its rows.
DROP TABLE "c_regions";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
