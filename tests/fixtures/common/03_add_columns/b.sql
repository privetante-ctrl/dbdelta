CREATE TABLE users (
    id integer PRIMARY KEY,
    email varchar(255) NOT NULL,
    nickname text,
    active boolean NOT NULL DEFAULT TRUE,
    score integer DEFAULT 0
);
