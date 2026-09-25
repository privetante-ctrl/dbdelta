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

COMMIT;
