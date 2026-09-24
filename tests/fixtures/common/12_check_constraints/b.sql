CREATE TABLE orders (
    id integer PRIMARY KEY,
    quantity integer NOT NULL,
    price numeric(10,2) NOT NULL,
    CHECK (quantity >= 0),
    CONSTRAINT orders_price_positive CHECK (price > 0)
);
