-- The schema of a small shop as it runs in production.
CREATE TYPE order_status AS ENUM ('new', 'paid', 'shipped');

CREATE TABLE customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email varchar(255) NOT NULL,
    full_name text NOT NULL,
    phone text
);

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
    created timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    order_id bigint NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id bigint NOT NULL REFERENCES products (id),
    quantity integer NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
