CREATE TABLE authors (id integer PRIMARY KEY);
CREATE TABLE books (
    id integer PRIMARY KEY,
    author_id integer REFERENCES authors (id) ON DELETE CASCADE
);
CREATE TABLE reviews (
    id integer PRIMARY KEY,
    book_id integer REFERENCES books (id) ON DELETE SET NULL
);
