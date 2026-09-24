CREATE TABLE c_regions (id integer PRIMARY KEY);
CREATE TABLE b_customers (
    id integer PRIMARY KEY,
    region_id integer NOT NULL REFERENCES c_regions (id)
);
CREATE TABLE a_invoices (
    id integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES b_customers (id)
);
