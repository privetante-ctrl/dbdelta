CREATE TYPE mood AS ENUM ('sad', 'meh', 'ok', 'happy');
CREATE TABLE entries (
    id integer PRIMARY KEY,
    mood mood NOT NULL DEFAULT 'ok',
    history mood[]
);
