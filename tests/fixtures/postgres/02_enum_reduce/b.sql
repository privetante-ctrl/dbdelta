CREATE TYPE mood AS ENUM ('happy', 'ok', 'sad');
CREATE TABLE entries (
    id integer PRIMARY KEY,
    mood mood NOT NULL DEFAULT 'ok',
    history mood[]
);
