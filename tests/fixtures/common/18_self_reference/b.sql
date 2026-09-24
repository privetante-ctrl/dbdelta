CREATE TABLE categories (
    id integer PRIMARY KEY,
    name text NOT NULL,
    parent_id integer REFERENCES categories (id)
);
CREATE TABLE comments (
    id integer PRIMARY KEY,
    reply_to integer REFERENCES comments (id),
    body text NOT NULL
);
