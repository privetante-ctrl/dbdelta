CREATE TABLE users (
    id integer PRIMARY KEY,
    email varchar(255) NOT NULL,
    legacy_code text,
    note text
);
CREATE INDEX ix_users_legacy ON users (legacy_code);
