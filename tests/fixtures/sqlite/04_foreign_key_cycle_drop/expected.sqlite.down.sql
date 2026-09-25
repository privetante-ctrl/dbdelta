BEGIN;

-- create table departments
-- IRREVERSIBLE: The up migration dropped table departments with its rows; this creates it again,
--   empty.
CREATE TABLE "departments" (
    "id" integer NOT NULL,
    "manager_id" integer,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("manager_id") REFERENCES "employees" ("id")
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

COMMIT;
