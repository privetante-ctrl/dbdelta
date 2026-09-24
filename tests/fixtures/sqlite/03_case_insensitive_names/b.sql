CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT,
    name TEXT
);
CREATE INDEX ix_users_email ON users (email);
