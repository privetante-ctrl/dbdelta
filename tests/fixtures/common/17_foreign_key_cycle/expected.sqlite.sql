BEGIN;

-- create table departments
CREATE TABLE "departments" (
    "id" integer NOT NULL,
    "manager_id" integer,
    PRIMARY KEY ("id"),
    CONSTRAINT "departments_manager_fkey" FOREIGN KEY ("manager_id") REFERENCES "employees" ("id")
);

-- create table employees
CREATE TABLE "employees" (
    "id" integer NOT NULL,
    "department_id" integer,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("department_id") REFERENCES "departments" ("id")
);

COMMIT;
