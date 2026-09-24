CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    name TEXT,
    price INTEGER,
    note TEXT
);
CREATE INDEX ix_items_name ON items (name);
