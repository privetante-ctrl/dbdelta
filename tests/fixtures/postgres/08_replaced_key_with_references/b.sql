CREATE TABLE customers (
    id integer,
    CONSTRAINT customers_pkey PRIMARY KEY (id)
);
CREATE TABLE orders (
    id integer PRIMARY KEY,
    customer_id integer REFERENCES customers (id)
);
