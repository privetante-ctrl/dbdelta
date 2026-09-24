BEGIN;

-- create table c_regions
CREATE TABLE "c_regions" (
    "id" integer NOT NULL,
    PRIMARY KEY ("id")
);

-- create table b_customers
CREATE TABLE "b_customers" (
    "id" integer NOT NULL,
    "region_id" integer NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("region_id") REFERENCES "c_regions" ("id")
);

-- create table a_invoices
CREATE TABLE "a_invoices" (
    "id" integer NOT NULL,
    "customer_id" integer NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("customer_id") REFERENCES "b_customers" ("id")
);

COMMIT;
