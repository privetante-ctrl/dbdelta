CREATE TABLE products (
    id integer PRIMARY KEY,
    sku text NOT NULL,
    name text NOT NULL,
    UNIQUE (name)
);
