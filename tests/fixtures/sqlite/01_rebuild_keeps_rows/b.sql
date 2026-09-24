CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    price REAL NOT NULL DEFAULT 0 CHECK (price >= 0),
    note TEXT
);
CREATE INDEX ix_items_name ON items (name DESC);
