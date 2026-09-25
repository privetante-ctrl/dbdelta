BEGIN;

-- create table departments
CREATE TABLE "departments" (
    "id" integer NOT NULL,
    "manager_id" integer,
    PRIMARY KEY ("id")
);

-- create table employees
-- IRREVERSIBLE: The up migration dropped table employees with its rows; this creates it again,
--   empty.
CREATE TABLE "employees" (
    "id" integer NOT NULL,
    "department_id" integer,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("department_id") REFERENCES "departments" ("id")
);

-- add foreign key departments_manager_fkey departments (manager_id) -> employees (id)
ALTER TABLE "departments" ADD CONSTRAINT "departments_manager_fkey" FOREIGN KEY ("manager_id") REFERENCES "employees" ("id");

COMMIT;
