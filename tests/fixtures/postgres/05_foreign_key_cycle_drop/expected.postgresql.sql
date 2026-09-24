BEGIN;

-- drop foreign key departments_manager_fkey departments (manager_id) -> employees (id)
ALTER TABLE "departments" DROP CONSTRAINT "departments_manager_fkey";

-- drop table employees
DROP TABLE "employees";

-- drop table departments
DROP TABLE "departments";

COMMIT;
