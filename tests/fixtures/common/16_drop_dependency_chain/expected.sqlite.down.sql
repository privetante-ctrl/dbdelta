BEGIN;

-- create table c_regions
-- IRREVERSIBLE: The up migration dropped table c_regions with its rows; this creates it again,
--   empty.
CREATE TABLE "c_regions" (
    "id" integer NOT NULL,
    PRIMARY KEY ("id")
);

-- create table b_customers
-- IRREVERSIBLE: The up migration dropped table b_customers with its rows; this creates it again,
--   empty.
CREATE TABLE "b_customers" (
    "id" integer NOT NULL,
    "region_id" integer NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("region_id") REFERENCES "c_regions" ("id")
);

-- create table a_invoices
-- IRREVERSIBLE: The up migration dropped table a_invoices with its rows; this creates it again,
--   empty.
CREATE TABLE "a_invoices" (
    "id" integer NOT NULL,
    "customer_id" integer NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("customer_id") REFERENCES "b_customers" ("id")
);

COMMIT;
