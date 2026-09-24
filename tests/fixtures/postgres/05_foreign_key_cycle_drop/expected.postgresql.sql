BEGIN;

-- drop foreign key departments_manager_fkey departments (manager_id) -> employees (id)
ALTER TABLE "departments" DROP CONSTRAINT "departments_manager_fkey";

-- drop table employees
-- DANGER drop-table: Dropping employees permanently deletes all of its rows.
DROP TABLE "employees";

-- drop table departments
-- DANGER drop-table: Dropping departments permanently deletes all of its rows.
DROP TABLE "departments";

COMMIT;
