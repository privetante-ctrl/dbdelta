-- The schema the next release expects.
CREATE TYPE order_status AS ENUM ('new', 'paid', 'shipped', 'refunded');

CREATE TABLE customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email varchar(120) NOT NULL,
    full_name text NOT NULL,
    loyalty_tier text NOT NULL
);
CREATE UNIQUE INDEX ux_customers_email ON customers (lower(email));

CREATE TABLE products (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku varchar(64) NOT NULL UNIQUE,
    title text NOT NULL,
    price numeric(10, 2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers (id),
    status order_status NOT NULL DEFAULT 'new',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_orders_customer ON orders (customer_id);

CREATE TABLE order_items (
    order_id bigint NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id bigint NOT NULL REFERENCES products (id) ON DELETE RESTRICT,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);
