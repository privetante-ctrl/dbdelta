CREATE TABLE products (
    id integer PRIMARY KEY,
    sku text NOT NULL,
    name text NOT NULL,
    CONSTRAINT products_sku_unique UNIQUE (sku)
);
